# Total-order beam prune (candidate_totalorder_widebeam, H4) - first KEPT candidate

Mechanism: LP-duals-vs-uniform lambda judged by greedy profit -> ratio-sorted
decision sequence -> width-limited beam, W = clip(3e7*budget/(n*m), 64, cap)
with cap 20000*max(1,budget/5) at budget >= 2.5s else 9000*budget. H4 change vs
H3: the per-layer prune is an EXACT TOTAL ORDER (score desc, profit desc,
used-capacity lex asc, index asc) implemented as argpartition on the boundary
score + argsort of the {score >= thr} block + one memcmp-style argsort of
packed big-endian keys per tie run. Seeds (3 wide / 2 narrow) + greedy
incumbent -> polish (1-0, 1-1, drop-1/add-2 best-improvement) gated at
budget >= 0.8s, wide schedule at >= 2.5s.

- 2026-11-01, run 20261101T190407Z (full): score 0.9997 (1s 0.9995, 5s 0.9998),
  coverage 1.00, 20/20 ok, KEPT - first kept candidate of the loop (H1 0.99714,
  H2 0.99580, H3 0.999551). Set a new record on medium_2 (56143, +36), reference
  updated.
- The total-order prune delivered exactly what H3's diagnosis predicted: width
  is now MONOTONE. No pair regressed from 1s to 5s (H1 had -small_0/-tight_0,
  H3 had large_0 -140). 5x width gains: large_0 +60 (106788 -> 106848), large_1
  +97 (107454 -> 107551), medium_2 +47 (56096 -> 56143), all other pairs +0.

## Residual loss structure (where the 0.03% lives)

Per-pair ratios vs pre-run references (large_0 107005, large_1 107628,
medium_0 57225, medium_1 56549, medium_2 56107):

- large_0: 0.99797 @1s (gap 217) / 0.99853 @5s (gap 157)
- large_1: 0.99838 @1s (gap 174) / 0.99928 @5s (gap 77)
- medium_0: 0.99946 at BOTH budgets (gap 31; objective and polish_gain
  identical 57194/407 at 1s and 5s)
- medium_1: 0.99973 at BOTH budgets (gap 15; identical 56534/242)
- medium_2: 0.99980 @1s (gap 11) / 1.00064 @5s (new reference)
- small_0-2, tight_0-1: 1.0000 at both budgets (6/10 pairs at gap 0)

Roughly 75-80% of the remaining deficit is the large class; medium contributes
tiny flat gaps (31/15/11), m=5 classes are closed.

## The large-class mechanism: the beam loses to its own greedy seed

beam-only objective (final - polish_gain) vs greedy seed:

- large_0 @1s: 105543 vs 105753 (-210); @5s: 105520 (-233)
- large_1 @1s: 105771 vs 105872 (-101); @5s: 105509 (-363)

At m=30 EVERY wide-beam completion (W = 2000-10000) is below the plain greedy
incumbent, so the beam's direct contribution on large is negative and polish
does all the lifting (gain +1245/+1683 @1s, +1328/+2042 @5s; gain over greedy
+1035/+1582 @1s). On medium the beam-only result beats greedy (medium_0:
56787 vs 56663, +124). The LP-dual scalarized state ranking degrades between
m=10 and m=30 - consistent with the m-gradient in class-behavior.md, but now
measured directly as "beam worse than greedy", not just "smaller gains".

## Width and budget saturation

- Width is no longer binding anywhere: 5x width on large buys 60-97 of
  157-217 gap; on medium, 9000 -> 20000 plus an extra seed buys EXACTLY 0 on
  medium_0/medium_1 (identical objective and polish_gain at both budgets -
  the extra beam work is fully absorbed by duplicate/equal-quality states) and
  only +47 on medium_2.
- Budget utilization: mean wall 0.16s @1s (16%), 0.32s @5s (6%). Worst case
  large_0 @5s: 0.41s wall = 8% of budget; ~4.6s idle. layers_done = n/n on all
  20 pairs (the H4-era candidates no longer truncate layers on wall clock).
- Polish is now real where it was 0 in H3 (large +1245..+2042, medium
  157-407) but converges in milliseconds; on medium_0/1 the identical
  polish_gain at 1s and 5s shows the incumbent is bit-identical, so extra
  budget currently buys nothing outside the large class.
- Lambda choice: small_0 is the only pair where uniform wins the greedy judging
  (all others lp_duals); small_0 polish_gain = 0 and sits exactly at reference.
