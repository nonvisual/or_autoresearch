# MDKP instance classes: loss structure

Per-class ratio-to-reference for the H1 MDD-beam candidate (run
20261101T170721Z, full subset). Reference objectives: large_0 107005, large_1
107628, medium_0 57206, medium_1 56549, medium_2 56107, small_0 37472, small_1
36538, small_2 32260, tight_0 60879, tight_1 61400.

- small (n=100, m=5): SOLVED. Ratio 1.0000 on all three instances at BOTH
  budgets. The beam+polish fully closes even a 2% greedy gap (small_2 greedy is
  0.9802 of reference). No further work needed on this class.
- tight (n=250, m=5): near-solved, 0.9985 (tight_0) / 0.9990 (tight_1) at 5s.
  Width already sits at the 16000 cap; remaining gap is small and would need
  better ordering, not width.
- medium (n=250, m=10): 0.9967-0.9979 at 5s, and the class with the largest
  1s -> 5s improvement (+0.36% mean). The worst single (instance, budget) pair
  of the whole run is medium_1 @1s at 0.9920.
- large (n=500, m=30): the bottleneck. 0.9933 (large_0) / 0.9948 (large_1) at
  5s, absolute gaps of 712 and 565. Both 1s and 5s sit here; width increases
  are exhausted (see mdd-beam.md).
- Class ranking follows n*m / m: small and tight (m=5) are fine, medium (m=10)
  loses ~0.3%, large (m=30) loses ~0.6%. Two mechanisms degrade together as m
  grows: the width schedule W ~ budget/(n*m), and the compression of all m
  dimensions into one scalar lambda-aggregate for ordering and bounding.
- Greedy quality predicts final quality: the surrogate-ratio greedy's
  ratio-to-reference tracks the final ratio across instances (large_0 0.9415
  -> 0.9929, medium_1 0.9597 -> 0.9920 at 1s, medium_2 0.9516 -> 0.9939, small
  0.9802-0.9980 -> 1.0000). The beam closes most but not all of the greedy
  gap, so improving the multiplier vector lifts the whole pipeline (order,
  bound, and the greedy seed itself).
- Only two multiplier vectors are ever considered (uniform, residual-tilted)
  and the entire pipeline inherits the winner. For m=30 that 2-point lambda
  search is the thinnest link.

## Update after H3 (run 20261101T180626Z): only large and medium_1/2 still lose

- 2026-11-01: with HiGHS LP-dual multipliers in the surrogate order, small and
  tight are EXACTLY at reference at both budgets (7/10 pairs at gap 0), and
  medium_0 57225 is a new record set by this candidate (+19 over 57206), now
  the reference. All remaining loss: large_0 -113 @1s / -253 @5s, large_1
  -171 / -172, medium_1 -56 both budgets, medium_2 -11 both budgets.
- The m-scaling law survives but is much weaker: large (m=30) loses 0.11-0.24%,
  medium (m=10) 0.02-0.10%, m=5 classes 0.00%. Since widths on medium already
  sit at 12000-16000 (past the saturation point measured in mdd-beam.md), the
  residual gradient in m now tracks per-dim multiplier quality (30 duals to
  get right vs 5), not width.
- Budget non-monotonicity is now a large-class-only phenomenon (large_0 -140
  from 1s to 5s) and is a beam tie-break artifact, not a schedule flaw - see
  the H3 section of mdd-beam.md.
- The polish neighborhood (1-0, 1-1, drop-1/add-2) is exhausted: it improved
  exactly one of 20 pairs in this run. Further polish work needs a strictly
  larger neighborhood (drop-2/add-3 or ruin-and-recreate, cf. L7) to matter.

## Update after H4 (run 20261101T190407Z, first KEPT candidate)

- 2026-11-01: score 0.9997. Class picture sharpens: m=5 classes exactly at
  reference at BOTH budgets; medium (m=10) gaps are tiny and flat (31/15/11,
  medium_2 5s now the reference at 56143); large (m=30) holds ~75-80% of all
  remaining loss (gaps 217/174 @1s, 157/77 @5s). The m-gradient law survives.
- Correction to the H3 note above: the drop-1/add-2 polish is NOT universally
  exhausted - on H4's incumbents it pays +1245..+2042 on large. What stays
  true: it converges in milliseconds, so neighborhood DEPTH (not the move set)
  is the limit - cf. the "beam worse than greedy" diagnostic in
  total-order-beam.md for where large-class headroom actually sits.
