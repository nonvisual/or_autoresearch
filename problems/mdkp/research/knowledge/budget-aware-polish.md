# Budget-aware polish and the idle wall budget (candidate_budgetaware_polish, H7) - falsified

Mechanism: the kept H4 pipeline (total-order wide beam, seeds + greedy incumbent,
1-0 / 1-1 / drop-1-add-2 best-improvement polish) with the fixed polish-round
count replaced by a deterministic loop that keeps running polish/repair rounds
until wall >= 0.8 * time_budget. Idea L17's premise: extra polish rounds are
what the 1s medium objectives were missing.

## Verdict (run 20261101T204252Z, full) - the premise was wrong

- Objectives are BYTE-IDENTICAL to H4's full run (20261101T190407Z) on all 20
  (instance, budget) pairs - 0 differing cells. The loop runs, the extra rounds
  are exact no-ops, as the falsification predicted (a zero-gain round provably
  leaves state untouched).
- The recorded score drop (H7 0.999586 vs H4 0.999650) is pure reference
  ratchet bias (L16), not regression: H4's own full run raised medium_2
  56107 -> 56143, so H7 was scored against the harder reference. Live
  confirmation of L16 - compare candidates objective-wise, never by recorded
  scores across ratchet-moving evals.
- Fixed round caps were NEVER binding anywhere: the loop ran 6-12 total rounds
  with converged=3/3 @1s and 4/4 @5s, i.e. <= 3 rounds per seed on every
  instance tested. Polish converges to a strict local optimum of its
  neighborhood within its old 2-3 round caps, every time.
- H5 remains the objective-wise best candidate: >= H4/H7 on all 20 pairs,
  strictly better on 3 (large_0 +32/+10 @1s/@5s, large_1 +61 @1s).

## Where the remaining deficit lives (vs current reference)

- large_0: gap 217 @1s / 157 @5s (ratio 0.99797 / 0.99853) - ~60% of all
  remaining deficit
- large_1: gap 174 @1s / 77 @5s (0.99838 / 0.99928)
- medium_0: 31 at BOTH budgets; medium_1: 15 at BOTH budgets (objectives and
  polish_gain bit-identical across 5x width + extra seed - fully saturated)
- medium_2: 47 @1s, 0 @5s (the one medium pair the width schedule still moves)
- small_0-2, tight_0-1: 0 at both budgets (6/10 pairs at reference).

## Beam-bound, not polish-bound, everywhere

- layers_done = n/n on all 20 pairs; wall 0.11-0.43s = 6-43% of budget
  (mean 0.16s @1s, 0.33s @5s). Profiler: beam layer loop ~96% of wall, polish
  ~3% (~11ms over 9 rounds), import ~31ms.
- polish_gain at convergence: large_1 +1683/+2042, large_0 +1245/+1328,
  medium_0 +407, medium_1 +242, medium_2 +157, small_0 0. Polish is the only
  mechanism still moving large, and it finishes in milliseconds.

## Rule for successors (what idle budget can and cannot buy)

- MORE ROUNDS of the same neighborhood CANNOT spend the 57-94% idle wall
  budget: convergence is <= 3 rounds per seed and further rounds are provably
  no-ops (H7). Any budget-spending candidate must change WHAT is searched:
  a stronger/different neighborhood, a different accept rule, or a second
  search trajectory. Round counts, caps and deadlines are solved problems.
- Candidate ranking protocol: after any full run within ~1e-4 of best-so-far,
  recompute objective-wise against the current reference (L16) - H5 vs H4/H7
  is the standing example.
- The large class (n=500, m=30) is where every unused second and every
  unclaimed point sits; at m=30 the beam still completes below its own greedy
  seed (total-order-beam.md), so trajectory-level changes outrank width there.
