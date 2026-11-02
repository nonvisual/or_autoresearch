# MDD beam search (candidate_dd_beam, H1)

Mechanism (from the candidate source + run 20261101T170721Z logs): a
surrogate-ratio item order (winner of two multiplier vectors: uniform vs
residual-tilted, judged by greedy profit) feeds a layered restricted MDD whose
states are remaining-capacity vectors; exact duplicate merge by 64-bit hash of
the remaining vector; width truncation by profit + a fractional-knapsack bound
on the scalar lambda-aggregate; then 1-0 / 1-1 / (drop-1 add-2 when budget >=
2.5s) polish of the best plus top-3 tail states.

- 2026-11-01, run 20261101T170721Z (full): AUC 0.9971 (1.0s 0.9965, 5.0s
  0.9978), coverage 1.00, all 20 pairs ok. Below the 0.9983 bar.
- Width saturation: on large_0, 5x width (W=2000 @1s -> W=10000 over 2 passes
  @5s) bought +48 profit out of a 761 gap to reference (0.9929 -> 0.9933);
  large_1 bought exactly 0. Where m is large, beam WIDTH is not the binding
  constraint - the single scalar surrogate ORDER is.
- Budget idleness: mean wall 0.39s at the 1s budget (internal deadline 0.75s)
  and 0.64s at 5s (deadline 3.75s). The width formula W = 3e7*budget/(n*m)
  capped at 16000 is far below what the measured per-layer cost affords - a
  full 500-layer W=2000 pass on large_0 takes 0.2s, so roughly 3-18x more beam
  work fits in the same budget. No timeout risk observed (walls 0.24-0.58s).
- Non-monotone in budget: the 5s two-pass schedule (pass 1 at W//3, pass 2 at
  the rest with a refined lambda) made small_0 (37472 -> 37456) and tight_0
  (60842 -> 60788) WORSE than the 1s single wide pass. Passes do not carry the
  incumbent forward, and the split can leave both passes weaker than one wide
  pass. Budget increases must never reduce realized solution quality.
- The medium-class 1s -> 5s gain is the polish gate, not width: medium
  improved +123 / +262 / +224 (mean +0.36%) while width only went 12000 ->
  16000 (mostly absorbed by duplicate merging). The qualitative change at 5s
  is drop-1/add-2 (`do_pair`, gated at budget >= 2.5). At 1s that move class
  is disabled and medium_1 @1s (0.9920) is the single worst pair in the run.
- Runtime profile (from history learnings): import 22-40ms, ~95% of runtime in
  the vectorized beam core. Speedups to the beam core translate directly into
  affordable width or more polish restarts.

## H2 (candidate_polish1s, run 20261101T174414Z): gate drop did not fail - the width cut did

- 2026-11-01, run 20261101T174414Z (full): AUC 0.99580 (1.0s 0.99576, 5.0s
  0.99584), coverage 1.00, all 20 pairs ok. BELOW H1's 0.99714 (-0.00134).
  Discarded. H2 changed two things at once: pair gate 2.5s -> 0.8s, AND a
  rebuild that shrank the width schedule to W = clip(350*budget, 300, 6000)
  (350 @1s, 1750 @5s) vs H1's 2000-12000 @1s / 16000 @5s, dropping H1's
  refined second multiplier pass.
- Per-cell H1 -> H2 objectives: gains ONLY medium @1s (+9 / +67 / +105, the
  gate drop's target, so the gate itself works). Losses everywhere else:
  large_1 -657 @1s / -568 @5s, medium @5s -114 / -267 / -74, tight -67..-143,
  small -11..-38. Net regression.
- Smoking gun: large_1 @1s. H1 beam-only at W=2000 reached 107063; H2 beam at
  W=350 plus polish reached 106406, and the polish added exactly 0 there
  (1/3 candidates improved, no gain). The whole -657 is beam narrowing, not
  the polish.
- The polish is cheap and real where it runs (beam pass-2 -> final): +800
  large_0 @1s, +730 medium_2 @1s, +214 tight_0 @1s, +192 medium_0 @1s, +110
  medium_1 @1s, at 2-20ms wall. It is NOT burning time for nothing. But it is
  instance-specific: exactly 0 gain on large_1 (both budgets), all of small,
  and tight_1 @1s - same class, same n/m as large_0 (+800), so the gain
  depends on per-instance slack structure, not on class alone.
- Width saturates near the low end: raising width 350 -> 1750 (1s -> 5s) moved
  the beam pass-2 objective by only -2 .. +191 (<0.35%), and is non-monotone:
  medium_1 pass-2 56056 @1s vs 56054 @5s, and medium_1 final 56166 @1s vs
  56094 @5s. Keeping the ~350 best by the surrogate bound already captures
  nearly the whole restricted frontier; extra width adds noise states, and
  the polish then runs on different, sometimes worse, incumbents.
- That non-monotonicity is why the 1s and 5s means are identical
  (0.99576 vs 0.99584): the width schedule is time-blind and the extra budget
  buys ~nothing, while utilization is 13% @1s (mean wall 0.13s) and 6% @5s
  (0.31s). Idle capacity is 0.7s @1s and 4.3s @5s on large.
- Verdict: beam width/quality, not the polish gate, is the dominant lever.
  Gate and width are not in real time conflict (polish costs milliseconds,
  walls are far under budget) - H2 lost because it PAID for the 1s polish by
  gutting the beam. H1's width schedule with H2's gate is the natural
  recombination.

## H3 (candidate_widebeam_polish, run 20261101T180626Z): LP-dual multipliers are the lever; width is not monotone

- 2026-11-01, run 20261101T180626Z (full): AUC 0.99955 (1.0s 0.9996, 5.0s
  0.9995), coverage 1.00, 20/20 ok. Best full score of the loop (H1 0.99714,
  H2 0.99580), yet discarded: its own smoke run had already raised medium_0
  57206 -> 57225, and the full run is then scored against that updated
  reference (delta -0.000615 vs the smoke row's 1.000166).
- The jump (+0.0024 over H1) comes from the multiplier upgrade alone - same
  width schedule, same 0.8s polish gate, but the second multiplier vector is
  HiGHS LP duals instead of the residual-tilted heuristic. Large class went
  0.9933/0.9948 -> 0.9989/0.9984. Confirms the "thinnest link" diagnosis in
  class-behavior.md.
- Width is NOT monotone: large_0 widened 2000 (@1s) -> 10000 (@5s) and FELL
  106892 -> 106752 (-140); large_1 107457 -> 107456 (-1). Medium width
  12000 -> 16000 changed nothing (objectives identical at both budgets), and
  small/tight are identical too. Mechanism: the per-layer prune keeps top-W by
  score = profit + residual*mr; with integer profits and residuals built from
  small-integer weight sums through a fixed lam, exact score ties at the prune
  boundary are frequent, and np.argpartition breaks them arbitrarily, so the
  surviving top-W set is not nested in W. A total-order tie-break (lexsort by
  score, then profit desc, then used-vector) would make top-W nested and
  widening safe.
- Polish (1-0 + 1-1 + drop-1/add-2, gate 0.8s) paid only on large_0 @1s
  (+432); zero everywhere else - at W >= 12000 the beam incumbent was already
  locally optimal under this neighborhood. The neighborhood is saturated; the
  residual gap is beam/order quality, not polish depth.
- Budget use: mean wall 0.19s @1s (19%) and 0.28s @5s (6%). Idle capacity at
  5s is ~4.7s - room for roughly 10x the scheduled beam work or a width
  ensemble.
- Unmeasured: the uniform-lam second beam's win rate (logs print only the
  final objective). One line of per-beam logging would show whether half the
  beam work is ever decisive.
