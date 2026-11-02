# Bottleneck-aware multi-item polish moves (candidate_bottleneck_polish, H8) - sound seed improver, zero objective movement

Mechanism: the kept H4/H7 pipeline (total-order wide beam, seeds + greedy
incumbent, 1-0 / 1-1 / drop-1-add-2 best-improvement polish) extended with two
moves run best-improvement after the existing ones (idea L18): (a) 2-1 swap -
drop the two incumbent items with worst profit per unit on the tightest
dimension, add the best fitting free item; (b) drop-2-add-2 restricted to item
pairs whose capacity footprint overlaps the binding constraint.

## Verdict (run 20261101T210131Z, full)

- Score 0.9996 (1s 0.9995, 5s 0.9997), coverage 1.00, all 20 pairs ok, no
  reference objective beaten, best-so-far 1.0002 unchanged. Objectives are
  identical to H4's on 19/20 pairs; the single change is large_0 @5s +12
  (106848 -> 106860, gap 157 -> 145).
- The 2-1 swap NEVER fired on any of the 20 pairs. Dead move.
- The drop-2-add-2 move does real work as a seed improver: ext_gain 148/178
  (large_0 @1s/@5s), 105/55 (large_1), 101 (medium_1), 28 (tight_0), 22
  (medium_0 @5s). None of it produced a new best objective.

## The key learning: per-seed gains get absorbed by seed diversity

- medium_0 @5s: polish_gain 471 and ext_gain 22 (vs 407/0 @1s) while the
  objective is bit-identical 57194 at BOTH budgets. The moves genuinely
  improved seeds by +22..+64 and the final answer did not move - the best seed
  already sat above every improved one.
- Same shape at large_1: polish_gain 1683 -> 2252 @5s (+569 of accepted moves)
  bought +97 objective.
- Conclusion: after the pipeline's convergence point, a STRONGER move set is a
  seed improver, not an objective mover. Move effort spent on non-incumbent
  seeds is wasted; the incumbent never sees the improvement.

## Budget behavior (unchanged from H7)

- layers_done = n/n on all 20 pairs; mean wall 0.20s @1s (20%), 0.45s @5s
  (9%) - 80-91% of the budget idle.
- The 5s pass still buys points, but through the old lever (third seed,
  beam_seeds 2 -> 3): large_0 +72, large_1 +97, medium_2 +47 (= reference,
  the only medium pair the width schedule moves). Nothing came from the new
  moves.

## Current deficit map (vs reference, after H8)

- large_0 -217 @1s / -145 @5s; large_1 -174 / -77; medium_0 -31 at BOTH
  budgets (saturated since H4); medium_1 -15 at both; medium_2 -47 / 0;
  small_0-2, tight_0-1 at reference (6/10 pairs).
- The large class holds ~80% of the remaining deficit at both budgets.

## Rules for successors

- Do not iterate on move-set extensions alone: after convergence they only
  improve seeds that do not determine the objective. Aim the extra descent at
  the incumbent only, combine per-seed optima (L20), or change trajectory
  (L19).
- Ranking refinements of the moves (L22) can only pay if absorption is
  addressed first - or if the ranking finds gains so large they exceed the
  seed that absorbs them.
- Objective-wise comparison stands (L16): H8 equals H4/H7 on 19/20 cells but
  its score is reported against a ratchet-raised reference.
