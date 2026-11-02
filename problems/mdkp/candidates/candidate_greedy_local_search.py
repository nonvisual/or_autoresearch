"""Candidate H3: surrogate-ratio greedy + best-improvement local search.

Constructive phase is baseline_greedy.py verbatim (surrogate-ratio order over
the tightest normalized resource usage, feeding a per-dimension ``remaining``
slack array). Local search then exploits that slack state with three strictly
improving, best-improvement neighborhoods:

- insert (1-0): add the max-profit unselected item that fits in every dimension;
- swap (1-1): drop one selected item, add the best unselected item that fits in
  the freed slack (vectorized feasibility scan ``w_j <= remaining + w_e``);
- drop-add (2-1): drop one selected item, add the best feasible pair.

Rounds of insert -> swap -> drop-add repeat until a full round has no improving
move (or the safety deadline). Every move strictly increases total profit, so
the incumbent is monotone and the final state is the best solution seen.
Deterministic: no randomness, ascending index iteration, strict ``>`` gain
checks and first-max numpy tie-breaks; wall-clock is only a safety cap and is
never reached on these instance sizes (convergence in well under 0.2 s).
"""

import sys
import time

import numpy as np

from problems.mdkp.problem import MDKPSolution

# Fraction of time_budget_s used as the internal deadline. The harness kills at
# budget * 1.25 measured from process start (import included), so the remaining
# 40% covers interpreter start, numpy import and the return path.
_TIME_SAFETY = 0.6
# Bound on elements of one feasibility tensor chunk (memory guard; chunking is
# fixed-size, hence deterministic).
_CHUNK_ELEMS = 4_000_000


def _constructive(values, weights, caps):
    """baseline_greedy.py constructive phase, verbatim semantics.

    Returns (remaining, in_sol): the per-dimension slack array and the
    selected-item mask of the surrogate-ratio greedy packing.
    """
    n = values.shape[0]
    caps_f = caps.astype(float)
    usage = (weights / caps_f[:, None]).max(axis=0)      # tightest-dimension load
    keys = values / np.maximum(usage, 1e-12)
    order = np.argsort(-keys, kind="stable")             # deterministic tie-breaks
    remaining = caps.copy()
    in_sol = np.zeros(n, dtype=bool)
    for j in order:
        w = weights[:, j]
        if np.all(w <= remaining):
            remaining -= w
            in_sol[int(j)] = True
    return remaining, in_sol


def _insert_pass(values, weights, remaining, in_sol, deadline):
    """1-0 adds: repeatedly take the max-profit unselected item that fits.

    Returns the total profit added (0 when no strictly improving add exists).
    """
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
        k = int(np.argmax(prof))                          # first max = lowest index
        if prof[k] <= 0:
            break                                         # strict improvement only
        j = int(unsel[cand[k]])
        in_sol[j] = True
        remaining -= weights[:, j]
        profit += int(prof[k])
    return profit


def _swap_pass(values, weights, remaining, in_sol, deadline):
    """Best-improvement 1-for-1 swap over a vectorized feasibility scan.

    For every selected e, candidate j is feasible iff w_j <= remaining + w_e in
    every dimension; the best (drop, add) pair by strict profit gain is applied.
    Returns the gain (0 when no improving swap exists).
    """
    sel = np.flatnonzero(in_sol)
    unsel = np.flatnonzero(~in_sol)
    if sel.size == 0 or unsel.size == 0 or time.perf_counter() >= deadline:
        return 0
    base = remaining[None, :] + weights[:, sel].T         # (|S|, m) freed slack
    w_unsel = weights[:, unsel].T                         # (|U|, m)
    p_unsel = values[unsel]                               # (|U|,)
    # Fixed-size row chunking keeps the tensor bounded; ascending order makes
    # the chunk sweep deterministic and first-max ties resolve to lowest e.
    rows_per_chunk = max(1, _CHUNK_ELEMS // max(1, unsel.size * weights.shape[0]))
    best_gain = 0
    best_move = None
    for start in range(0, sel.size, rows_per_chunk):
        if time.perf_counter() >= deadline:
            break
        chunk = base[start:start + rows_per_chunk]
        feas = np.all(w_unsel[None, :, :] <= chunk[:, None, :], axis=2)   # (c, |U|)
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
    """Best-improvement drop-1/add-2 move.

    For every selected e, candidates are the unselected items that individually
    fit in the freed slack; the best feasible pair (a, b) among them is found by
    an upper-triangular vectorized scan, and the move is kept iff
    p_a + p_b > p_e. Returns the gain (0 when no improving move exists).
    """
    # ``in_sol`` is not modified inside the scan (moves apply after the loop), so
    # the unselected set and its weight/profit slices are loop-invariant.
    unsel = np.flatnonzero(~in_sol)
    if unsel.size < 2:
        return 0
    w_unsel = weights[:, unsel]                            # (m, |U|)
    p_unsel = values[unsel]
    cols = np.arange(unsel.size)
    tri = cols[None, :] > cols[:, None]                    # strict upper triangle
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
        w_cand = w_unsel[:, fits]                          # (m, K)
        # Row-blocked pair scan: every ordered pair (a, b) with b > a appears
        # exactly once, in the row block of its smaller index (fixed blocks,
        # ascending a -> deterministic, first-max ties resolve to lowest a, b).
        block = max(1, _CHUNK_ELEMS // max(1, m_dim * k))
        # Reused per-e buffers: the (m, B, K) feasibility tensor and its (B, K)
        # dimension-reduction (same booleans as ``np.all(..., axis=0)`` on the
        # freshly broadcast tensor, without re-allocating per block).
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


def solve(instance, time_budget_s):
    t0 = time.perf_counter()
    values = np.asarray(instance.values, dtype=np.int64)
    weights = np.asarray(instance.weights, dtype=np.int64)   # (m, n)
    caps = np.asarray(instance.capacities, dtype=np.int64)

    remaining, in_sol = _constructive(values, weights, caps)
    best_mask = in_sol.copy()
    best_obj = int(values[in_sol].sum())
    obj = best_obj

    try:
        budget = float(time_budget_s)
    except (TypeError, ValueError):
        budget = 0.0
    if not np.isfinite(budget) or budget <= 0.0:
        budget = 0.0
    deadline = t0 + budget * _TIME_SAFETY

    rounds = 0
    while time.perf_counter() < deadline:
        rounds += 1
        improved = False
        gain = _insert_pass(values, weights, remaining, in_sol, deadline)
        if gain > 0:
            improved = True
            obj += gain
            if obj > best_obj:
                best_obj, best_mask = obj, in_sol.copy()
        while time.perf_counter() < deadline:
            gain = _swap_pass(values, weights, remaining, in_sol, deadline)
            if gain <= 0:
                break
            improved = True
            obj += gain
            if obj > best_obj:
                best_obj, best_mask = obj, in_sol.copy()
        while time.perf_counter() < deadline:
            gain = _pair_pass(values, weights, remaining, in_sol, deadline)
            if gain <= 0:
                break
            improved = True
            obj += gain
            if obj > best_obj:
                best_obj, best_mask = obj, in_sol.copy()
        if not improved:
            break

    selected = sorted(int(j) for j in np.flatnonzero(best_mask))
    print(
        f"[candidate_greedy_local_search] rounds={rounds} obj={best_obj} "
        f"items={len(selected)} wall={time.perf_counter() - t0:.3f}s "
        f"budget={budget:.3f}s",
        file=sys.stderr,
    )
    return MDKPSolution(selected)
