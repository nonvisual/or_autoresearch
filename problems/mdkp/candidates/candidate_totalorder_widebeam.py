"""Candidate H4: total-order wide beam with LP-dual lambda guidance.

Reconstruction of the discarded wide-beam pipeline (H1/H3 mechanism) plus the
H4 change family (beam prune + width):

1. Lambda guidance from the LP relaxation: HiGHS solves the continuous MDKP
   and the m row duals become the lagrangian multiplier vector. A second,
   uniform multiplier vector (lambda_i = 1/c_i) is scored by surrogate-ratio
   greedy profit; the winner (higher greedy profit, LP duals on ties) supplies
   the beam item order and the beam scoring aggregate (cheap second pass).
2. Width-limited beam over the ratio-sorted decision sequence,
   W = clip(3e7 * budget / (n*m), floor, cap). The cap keeps the raised
   20000 * max(1, budget/5) shape for budget >= 2.5 s; below that it is scaled
   down (9000 * budget at 1 s) so the total-order prune provably finishes all
   n layers inside the schedule instead of truncating at a timing-dependent
   layer (which broke rerun identity).
3. THE H4 CHANGE: the per-layer prune is a TOTAL ORDER sort + prefix cut.
   Candidates are ordered by (score desc, profit desc, used-capacity vector
   lex asc, candidate index asc), where score = profit + fractional-knapsack
   bound of the lambda-aggregated remaining capacity over the ratio-ordered
   tail. The top-W of that order is a prefix: increasing W can only add states
   (nesting), never reshuffle them the way an argpartition boundary did in H3.
   It is built in cheap steps that are provably identical to sorting all
   candidates with the full key tuple: np.argpartition on -score at position
   W-1 yields the boundary score thr; candidates with score < thr can never
   enter the prefix, so the block {score >= thr} (boundary ties included in
   full) is argsorted by score and only its EXACT tie runs are reordered by
   (profit desc, used lex asc, index asc) - bit-identical to lexsorting the
   whole block, but the expensive multi-key pass touches only tied elements.
   Tie runs are refined either by packing (run id, sign-biased profit, used
   dims) into big-endian byte rows sorted by one stable memcmp argsort
   (bytewise order on big-endian uint32 fields equals numeric field lex, one
   pass instead of m + 2), or by np.lexsort when magnitudes exceed the uint32
   packing bounds; both were verified equal to the full-key lexsort on
   randomized tie-heavy inputs. Elements outside the block sort strictly
   behind it, so the resulting prefix equals the full sort's prefix.
4. Bookkeeping fixes: add candidates are compressed to feasible parents
   (``used_add = used[fa_idx] + w``), so an add candidate at concatenated
   index ``S + k`` descends from previous-layer state ``fa_idx[k]``; parents
   are recorded as ``fa_idx[keep - S]`` (skip states keep ``keep``). The kept
   states are also sliced from a single aligned candidate array ``used_c``
   (previous code rebuilt ``used`` as skip-rows-then-add-rows while
   profit/lamu stayed in keep order, misaligning used vectors with their
   states), which restores "every kept state is feasible by construction" and
   makes the backtracked seeds genuine beam paths. Seeds are item-INDEX
   arrays end to end and the returned selection is those indices directly
   (the previous np.flatnonzero(best_mask) re-masked an index array and
   returned a corrupted, infeasible set).
5. Polish (fires only when budget >= 0.8 s, the H2/H3 gate): exhaustive
   best-improvement 1-0 add, 1-1 swap and drop-1/add-2 rounds on the top beam
   states plus the greedy seed, with deterministic round caps and a hard stop
   before the deadline.

Determinism: no randomness anywhere; stable/total-order sorts only; the
schedule (width, seeds, round caps) is a pure function of (n, m, budget) and
is driven by iteration counts (layers, rounds). The wall clock is only a
safety cap that the measured schedules never reach; a stderr diagnostic
reports layers_done=t/n for verification.
"""

import math
import sys
import time

import numpy as np

from problems.mdkp.problem import MDKPSolution

try:
    import highspy
except Exception:  # pragma: no cover - uniform-lambda fallback path
    highspy = None

# ----------------------------------------------------------------- schedule --
# The harness kills at budget * 1.25 measured from process start; imports are
# ~0.1 s, so solve() keeps an internal deadline well inside its own budget.
_WIDTH_NUM = 3.0e7          # H1/H3 width schedule: W = NUM * budget / (n*m)
_WIDTH_CAP_WIDE = 20000     # H4 cap at wide budgets (H1/H3 capped at 16000)
_WIDTH_CAP_MULT_MAX = 4.0   # budget-scaled cap headroom bound
_WIDTH_CAP_FAST = 9000      # cap scale at 1 s: total-order prune fits all layers
_WIDTH_SLOW_BUDGET = 2.5    # budget threshold for the wide cap
_WIDTH_FLOOR = 64
_POLISH_GATE_S = 0.8        # polish fires only when budget >= 0.8 s
_WIDE_BUDGET = 2.5          # budget threshold for the larger polish schedule
_SEEDS_WIDE, _SEEDS_NARROW = 3, 2
_ROUNDS_WIDE, _ROUNDS_NARROW = 3, 2
_CHUNK_ELEMS = 4_000_000    # bounded feasibility tensors in the polish scans


def _deadline(t0, budget):
    if budget <= 0.0:
        return t0
    return t0 + max(0.05, min(0.85 * budget, budget - 0.35))


def _width(n, m, budget):
    w = _WIDTH_NUM * budget / float(n * m)
    if budget >= _WIDTH_SLOW_BUDGET:
        cap = _WIDTH_CAP_WIDE * min(_WIDTH_CAP_MULT_MAX, max(1.0, budget / 5.0))
    else:
        # small budgets: the exact total-order prune is slower per layer than
        # the old argpartition prune, so scale the cap down (a pure function of
        # budget) instead of truncating layers on wall-clock feedback.
        cap = _WIDTH_CAP_FAST * max(0.0, budget)
    return int(max(_WIDTH_FLOOR, min(w, cap)))


# ------------------------------------------------------------- LP dual guide --
def _lp_duals(values, weights, caps, budget):
    """Row duals of the continuous relaxation (None on any failure)."""
    if highspy is None:
        return None
    n, m = values.shape[0], caps.shape[0]
    try:
        h = highspy.Highs()
        h.setOptionValue("output_flag", False)
        # Generous limit: the LP is tiny (9 ms at n=500, m=30). A limit hit is
        # treated as a failure so behaviour stays deterministic.
        h.setOptionValue("time_limit", 0.5)
        lp = highspy.HighsLp()
        lp.num_col_ = n
        lp.num_row_ = m
        lp.col_cost_ = values.astype(np.double)
        lp.col_lower_ = np.zeros(n)
        lp.col_upper_ = np.ones(n)
        lp.row_lower_ = np.full(m, -highspy.kHighsInf)
        lp.row_upper_ = caps.astype(np.double)
        lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
        lp.a_matrix_.start_ = np.arange(n + 1, dtype=np.int32) * m
        lp.a_matrix_.index_ = np.tile(np.arange(m, dtype=np.int32), n)
        lp.a_matrix_.value_ = weights.astype(np.double).T.ravel()
        lp.sense_ = highspy.ObjSense.kMaximize
        h.passModel(lp)
        h.run()
        if h.getModelStatus() != highspy.HighsModelStatus.kOptimal:
            return None
        duals = np.asarray(h.getSolution().row_dual, dtype=float)
        if duals.size < m or not np.all(np.isfinite(duals[:m])):
            return None
        duals = duals[:m]
        if duals.max() <= 0.0:          # normalize sign convention
            duals = -duals
        duals = np.maximum(duals, 0.0)
        if duals.sum() <= 0.0:
            return None
        return duals
    except Exception:
        return None


def _greedy(values, weights, caps, rw):
    """Add-while-fits greedy in profit / lambda-weight order."""
    keys = values / np.maximum(rw, 1e-12)
    order = np.argsort(-keys, kind="stable")
    remaining = caps.copy()
    in_sol = np.zeros(values.shape[0], dtype=bool)
    for j in order:
        w = weights[:, int(j)]
        if np.all(w <= remaining):
            remaining -= w
            in_sol[int(j)] = True
    return in_sol, int(values[in_sol].sum())


# -------------------------------------------------------------------- polish --
def _insert_pass(values, weights, remaining, in_sol, deadline):
    """1-0 adds: repeatedly take the max-profit unselected item that fits."""
    profit = 0
    while time.perf_counter() < deadline:
        unsel = np.flatnonzero(~in_sol)
        if unsel.size == 0:
            break
        fits = np.all(weights[:, unsel] <= remaining[:, None], axis=0)
        cand = np.flatnonzero(fits)
        if cand.size == 0:
            break
        prof = values[unsel[cand]]
        k = int(np.argmax(prof))                    # first max = lowest index
        if prof[k] <= 0:
            break
        j = int(unsel[cand[k]])
        in_sol[j] = True
        remaining -= weights[:, j]
        profit += int(prof[k])
    return profit


def _swap_pass(values, weights, remaining, in_sol, deadline):
    """Best-improvement 1-for-1 swap (vectorized feasibility scan)."""
    sel = np.flatnonzero(in_sol)
    unsel = np.flatnonzero(~in_sol)
    if sel.size == 0 or unsel.size == 0 or time.perf_counter() >= deadline:
        return 0
    base = remaining[None, :] + weights[:, sel].T          # (|S|, m) freed slack
    w_unsel = weights[:, unsel].T                          # (|U|, m)
    p_unsel = values[unsel]
    rows_per_chunk = max(1, _CHUNK_ELEMS // max(1, unsel.size * weights.shape[0]))
    best_gain = 0
    best_move = None
    for start in range(0, sel.size, rows_per_chunk):
        if time.perf_counter() >= deadline:
            break
        chunk = base[start:start + rows_per_chunk]
        feas = np.all(w_unsel[None, :, :] <= chunk[:, None, :], axis=2)
        masked = np.where(feas, p_unsel[None, :], np.int64(-1))
        best_j = np.argmax(masked, axis=1)
        rows = np.arange(chunk.shape[0])
        best_p = masked[rows, best_j]
        gains = best_p - values[sel[start:start + chunk.shape[0]]]
        e_local = int(np.argmax(gains))
        if int(gains[e_local]) > best_gain:
            best_gain = int(gains[e_local])
            best_move = (int(sel[start + e_local]), int(unsel[best_j[e_local]]))
    if best_move is None or best_gain <= 0:
        return 0
    drop, add = best_move
    in_sol[drop] = False
    in_sol[add] = True
    remaining += weights[:, drop]
    remaining -= weights[:, add]
    return best_gain


def _pair_pass(values, weights, remaining, in_sol, deadline):
    """Best-improvement drop-1 / add-2 move (row-blocked pair scan)."""
    unsel = np.flatnonzero(~in_sol)
    if unsel.size < 2:
        return 0
    w_unsel = weights[:, unsel]
    p_unsel = values[unsel]
    cols = np.arange(unsel.size)
    tri = cols[None, :] > cols[:, None]
    best_gain = 0
    best_move = None
    m_dim = weights.shape[0]
    for e in np.flatnonzero(in_sol):
        if time.perf_counter() >= deadline:
            break
        free = remaining + weights[:, e]
        fits = np.all(w_unsel <= free[:, None], axis=0)
        cand = unsel[fits]
        k = cand.size
        if k < 2:
            continue
        p_cand = p_unsel[fits]
        w_cand = w_unsel[:, fits]
        block = max(1, _CHUNK_ELEMS // max(1, m_dim * k))
        tens = np.empty((m_dim, block, k), dtype=bool)
        acc = np.empty((block, k), dtype=bool)
        for a0 in range(0, k - 1, block):
            if time.perf_counter() >= deadline:
                break
            a1 = min(k, a0 + block)
            feas = tens[:, :a1 - a0]
            np.less_equal(w_cand[:, None, :],
                          (free[:, None] - w_cand[:, a0:a1])[:, :, None], out=feas)
            pair_ok = np.logical_and.reduce(feas, axis=0, out=acc[:a1 - a0])
            pair_ok &= tri[a0:a1, :k]
            tot = np.where(pair_ok, p_cand[a0:a1, None] + p_cand[None, :], np.int64(-1))
            flat = int(np.argmax(tot))
            bi, bj = flat // tot.shape[1], flat % tot.shape[1]
            gain = int(tot[bi, bj]) - int(values[e])
            if gain > best_gain:
                best_gain = gain
                best_move = (int(e), int(cand[a0 + bi]), int(cand[bj]))
    if best_move is None or best_gain <= 0:
        return 0
    e, a, b = best_move
    in_sol[e] = False
    remaining += weights[:, e]
    in_sol[a] = True
    remaining -= weights[:, a]
    in_sol[b] = True
    remaining -= weights[:, b]
    return best_gain


def _polish_seed(values, weights, caps, seed, deadline, rounds_cap):
    """Best-improvement local search from one seed; returns (mask, profit)."""
    in_sol = np.zeros(values.shape[0], dtype=bool)
    if seed.size:
        in_sol[seed] = True
    remaining = caps - weights[:, in_sol].sum(axis=1)
    obj = int(values[in_sol].sum())
    rounds = 0
    while rounds < rounds_cap and time.perf_counter() < deadline:
        rounds += 1
        improved = False
        gain = _insert_pass(values, weights, remaining, in_sol, deadline)
        if gain > 0:
            improved = True
            obj += gain
        while time.perf_counter() < deadline:
            gain = _swap_pass(values, weights, remaining, in_sol, deadline)
            if gain <= 0:
                break
            improved = True
            obj += gain
        while time.perf_counter() < deadline:
            gain = _pair_pass(values, weights, remaining, in_sol, deadline)
            if gain <= 0:
                break
            improved = True
            obj += gain
        if not improved:
            break
    return in_sol, obj


# ----------------------------------------------------------------- beam core --
def _pack_tie_keys(run_id, profit, rows, m):
    """Pack (run asc, profit desc, used lex asc) into one byte row per element.

    Big-endian uint32 fields compared bytewise (numpy 'V' memcmp order) are
    numerically ordered exactly like the fields themselves, and a leading
    field dominates, so ONE stable argsort over the packed rows reproduces
    np.lexsort with the key tuple (run_id asc, -profit asc, used_0..m-1 asc)
    - byte for byte the same permutation (stability keeps ascending candidate
    index for fully identical rows). This replaces a (m + 2)-key lexsort of
    the tied block, which dominates per-layer time on tie-heavy layers
    (m * O(k log k) memcmp passes vs one).
    """
    k = rows.shape[0]
    packed = np.empty((k, m + 2), dtype=np.uint32)
    packed[:, 0] = run_id.astype(np.uint32)
    # profit desc as ascending unsigned: bias by the sign bit so that
    # 0x80000000 - profit is monotone decreasing in profit (plain two's
    # complement patterns would order profit 0 before profit 2)
    packed[:, 1] = (np.int64(0x80000000) - profit).astype(np.uint32)
    packed[:, 2:] = rows.astype(np.uint32)
    be = packed.astype('>u4')                       # big-endian byte layout
    flat = np.ascontiguousarray(be.view(np.uint8).reshape(k, -1))
    return flat.view(np.dtype(('V', 4 * (m + 2)))).ravel()


def _refine_ties(ord1, score, profit_c, used_c, m, void_ok):
    """Extend a score-descending sort to the H4 total order.

    Contiguous runs of EXACT score ties are reordered by (profit desc, used
    vector lex asc); fully identical candidates keep ascending candidate index
    (stable sorts). This is the same permutation np.lexsort would produce for
    the full key tuple (score desc, profit desc, used_0..used_{m-1} asc, index
    asc) - verified against a full-key lexsort on randomized tie-heavy inputs -
    but only the tied elements are sorted, which is a small fraction of the
    block whenever scores are continuous.
    """
    if ord1.size < 2:
        return ord1
    sS = score[ord1]
    adj = sS[1:] == sS[:-1]
    if not adj.any():
        return ord1
    starts = np.concatenate(([True], ~adj))
    gid = np.cumsum(starts) - 1
    gsize = np.bincount(gid, minlength=int(gid[-1]) + 1)
    multi = gsize >= 2
    if not multi.any():
        return ord1
    sel = np.flatnonzero(multi[gid])
    cand = ord1[sel]
    run_id = gid[sel]
    rows = used_c[cand]
    profit_tied = profit_c[cand]
    if void_ok:
        sub = np.argsort(_pack_tie_keys(run_id, profit_tied, rows, m),
                         kind="stable")
    else:                       # pathological magnitudes: plain lexsort path
        keys = tuple(rows[:, d] for d in range(m - 1, -1, -1))
        keys += (-profit_tied, run_id)
        sub = np.lexsort(keys)
    inv = np.empty(sub.size, dtype=np.int64)
    inv[sub] = np.arange(sub.size)
    prefix = np.concatenate(([0], np.cumsum(np.where(multi, gsize, 0))))
    rank_in_run = inv - prefix[run_id]
    gstart = np.concatenate(([0], np.cumsum(gsize)))
    newkey = np.arange(ord1.size, dtype=np.int64)
    newkey[sel] = gstart[run_id] + rank_in_run
    return ord1[np.argsort(newkey, kind="stable")]


def _beam(P, Wm, caps, lam_w, lam_cap, order, W, deadline, k_seeds):
    """Layered beam with the exact total-order prune.

    Returns (seed item arrays, layers_done). States are partial selections of
    the decision sequence; each layer decides item ``order[t]``. Layer ``t``'s
    candidates are rows ``[0, S)`` = previous states that skip the item and
    rows ``[S, S + A)`` = add states compressed to feasible parents (row
    ``S + k`` descends from previous-layer state ``fa_idx[k]``). Every kept
    state is feasible by construction, so the beam always retains at least the
    all-skip state and any partial state is a valid feasible solution if the
    safety deadline ever interrupts the run.
    """
    n = P.shape[0]
    m = Wm.shape[0]
    # packed-tie-key bounds: partial profits < 2**31 and any used entry (<= the
    # total weight of a dimension) < 2**32 keep the memcmp path exact
    void_ok = (int(P.sum()) < 2 ** 31
               and int(Wm.sum(axis=1).max()) < 2 ** 32)
    used = np.zeros((1, m), dtype=np.int64)
    profit = np.zeros(1, dtype=np.int64)
    lamu = np.zeros(1, dtype=np.float64)
    par_layers = []          # parent index in the previous layer, per kept state
    took_layers = []         # whether the layer's item was added, per layer
    n_last = 1               # states in the last completed layer's output
    layers_done = 0

    for t in range(n):
        if time.perf_counter() >= deadline:
            break
        wt = Wm[:, t]
        Pt = int(P[t])
        lwt = float(lam_w[t])
        fa = np.all(used <= caps - wt, axis=1)
        fa_idx = np.flatnonzero(fa)
        S = profit.shape[0]
        used_add = used[fa_idx] + wt
        profit_add = profit[fa_idx] + Pt
        lamu_add = lamu[fa_idx] + lwt
        # aligned candidate arrays: skips at [0, S), adds at [S, S + A)
        profit_c = np.concatenate((profit, profit_add))
        lamu_c = np.concatenate((lamu, lamu_add))
        used_c = np.empty((S + fa_idx.size, m), dtype=np.int64)
        used_c[:S] = used
        used_c[S:] = used_add

        # fractional-knapsack bound of the lambda-aggregated remaining capacity
        R = lam_cap - lamu_c
        rwp = lam_w[t:]
        pp = P[t:]
        cw = np.concatenate(([0.0], np.cumsum(rwp)))
        cp = np.concatenate(([0.0], np.cumsum(pp)))
        rat = np.concatenate((pp / np.maximum(rwp, 1e-12), [0.0]))
        k = np.searchsorted(cw, R, side="right") - 1
        ub = cp[k] + (R - cw[k]) * rat[k]
        score = profit_c + ub

        # Exact top-W prefix of the total order (score desc, profit desc, used
        # lex asc, candidate index asc). argpartition locates the boundary
        # score (the W-th largest); candidates strictly below it can never
        # enter the prefix and boundary-tied candidates are all kept, so the
        # sorted prefix of the block equals the sorted prefix of ALL
        # candidates while the sort touches only ~W elements instead of 2W.
        ncand = score.size
        if ncand > W:
            neg = -score
            thr = neg[np.argpartition(neg, W - 1)[W - 1]]
            blk = np.flatnonzero(neg <= thr)
        else:
            blk = np.arange(ncand)
        cut = min(W, ncand)
        ord1 = blk[np.argsort(-score[blk], kind="stable")]
        keep = _refine_ties(ord1, score, profit_c, used_c, m, void_ok)[:cut]

        is_skip = keep < S
        # parent of add candidate S+k is fa_idx[k], NOT k (np.where would
        # evaluate fa_idx[keep - S] for skips too, so index the add rows only)
        par = keep.astype(np.int32)
        par[~is_skip] = fa_idx[keep[~is_skip] - S]
        par_layers.append(par)
        took_layers.append(~is_skip)
        n_last = cut
        layers_done = t + 1
        used = used_c[keep]          # rows stay aligned with profit / lamu
        profit = profit_c[keep]
        lamu = lamu_c[keep]

    seeds = []
    seen = set()
    n_layers = len(par_layers)
    for rank in range(min(k_seeds, n_last)):
        idx = rank          # positions in the last completed layer's output
        items = []
        for l in range(n_layers - 1, -1, -1):
            if took_layers[l][idx]:
                items.append(int(order[l]))
            idx = int(par_layers[l][idx])
        key = tuple(sorted(items))
        if key not in seen:
            seen.add(key)
            seeds.append(np.fromiter(key, dtype=np.int64, count=len(key)))
    return seeds, layers_done


# --------------------------------------------------------------------- solve --
def solve(instance, time_budget_s):
    t0 = time.perf_counter()
    n, m = int(instance.n), int(instance.m)
    values = np.asarray(instance.values, dtype=np.int64)
    weights = np.asarray(instance.weights, dtype=np.int64)   # (m, n)
    caps = np.asarray(instance.capacities, dtype=np.int64)

    try:
        budget = float(time_budget_s)
    except (TypeError, ValueError):
        budget = 0.0
    if not math.isfinite(budget) or budget <= 0.0:
        budget = 0.0
    deadline = _deadline(t0, budget)

    # -- lambda guidance: LP duals vs uniform, judged by greedy profit
    lam_dual = _lp_duals(values, weights, caps, budget)
    lam_uni = 1.0 / caps.astype(np.float64)
    greedy_profit = -1
    greedy_mask = np.zeros(n, dtype=bool)
    lam_star = lam_uni
    lam_src = "uniform"
    for lam in (lam_dual, lam_uni):
        if lam is None:
            continue
        mask, prof = _greedy(values, weights, caps, lam @ weights)
        if prof > greedy_profit:
            greedy_profit = prof
            greedy_mask = mask
            lam_star = lam
            lam_src = "lp_duals" if lam is lam_dual else "uniform"

    # -- beam over the ratio-sorted decision sequence
    rw = lam_star @ weights
    keys = values / np.maximum(rw, 1e-12)
    order = np.argsort(-keys, kind="stable")
    P = values[order]
    Wm = np.ascontiguousarray(weights[:, order])
    lam_w = rw[order]
    lam_cap = float(lam_star @ caps)
    W = _width(n, m, budget)
    k_seeds = _SEEDS_WIDE if budget >= _WIDE_BUDGET else _SEEDS_NARROW
    beam_seeds, layers_done = _beam(P, Wm, caps, lam_w, lam_cap, order, W,
                                    deadline, k_seeds)

    # -- seeds: beam ranks first, then the greedy incumbent
    seeds = []
    seen = set()
    for mask in list(beam_seeds) + [np.flatnonzero(greedy_mask).astype(np.int64)]:
        key = mask.tobytes()
        if key not in seen:
            seen.add(key)
            seeds.append(mask)

    best_mask = None
    best_obj = -1
    for seed in seeds:
        obj = int(values[seed].sum())
        if obj > best_obj:
            best_obj, best_mask = obj, seed

    polish_gain = 0
    if budget >= _POLISH_GATE_S and seeds:
        rounds_cap = _ROUNDS_WIDE if budget >= _WIDE_BUDGET else _ROUNDS_NARROW
        for seed in seeds:
            if time.perf_counter() >= deadline:
                break
            mask, obj = _polish_seed(values, weights, caps, seed,
                                     deadline, rounds_cap)
            polish_gain += obj - int(values[seed].sum())
            if obj > best_obj:
                best_obj = obj
                best_mask = np.flatnonzero(mask).astype(np.int64)

    # best_mask is an ITEM-INDEX array (beam/greedy seeds and the polish
    # branch all store index arrays); never apply flatnonzero to it again
    selected = sorted(int(j) for j in best_mask)
    print(
        f"[totalorder_widebeam] n={n} m={m} W={W} lam={lam_src} "
        f"greedy={greedy_profit} beam_seeds={len(beam_seeds)} "
        f"polish_gain={polish_gain} obj={best_obj} "
        f"layers_done={layers_done}/{n} "
        f"wall={time.perf_counter() - t0:.3f}s budget={budget:.2f}s",
        file=sys.stderr,
    )
    return MDKPSolution(selected)
