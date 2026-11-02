# Path relinking over converged seed optima (candidate_relink_seeds, H9) - verdict: one basin, recombination cannot pay

Mechanism: the kept H4 total-order wide-beam pipeline unchanged, plus a final
deterministic phase: take pairs of converged seed optima, build crossover
starts from their symmetric difference (greedy-repaired in surrogate-ratio
order), re-polish each start with the UNCHANGED `_polish_seed`, accept only
strict improvements over the incumbent pool; wave agenda (wave 0 = all seed
pairs, later waves relink a new incumbent against the pool), capped at 6/10
relinks while wall < 0.8*budget.

## Run 20261101T211927Z (full): score 0.999586, discarded; zero objective movement

- Objectives are bit-identical to H4 on all 20 (instance, budget) pairs; no
  instance beat the reference. Gaps vs reference @5s: large_0 -157
  (106848/107005), large_1 -77 (107551/107628), medium_0 -31 (57194/57225),
  medium_1 -15 (56534/56549); medium_2 (56143), small_0-2 and tight_0-1 are
  exactly at reference (6/10 pairs). @1s additionally misses medium_2 by 47
  (56096).
- relink_hits=0, relink_gain=0, relink_waves=0 on all 20 pairs; 3 relinks at
  the 1s budget, 6 at 5s - the cap never bound.
- Wall use 0.15-0.54s of 1-5s budgets (85-93% idle), as in H4-H8.

## Artifact vs real signal: REAL signal

- An acceptance artifact (parity guaranteed by strict-improvement-only
  acceptance) would show relink_ends == incumbent. Instead every logged end is
  strictly BELOW the incumbent, and relink_ends is the best polished crossover
  of that pair: large_0 @1s ends [106723, 106450, 106638] vs obj 106788;
  large_0 @5s ends <= 106784 vs 106848; medium_1 @5s ends <= 56493 vs 56534;
  tight_1 @5s ends <= 61349 vs 61400; small_2 ends 32249 vs 32260. Children
  lose by 11-2000, they are not merely unaccepted equals.
- The operator DID explore: relink_diffs are non-zero nearly everywhere
  (16-38 items on large, 5-14 on medium/tight), so the crossovers were genuine
  new points, and after the same polish the parents got, they still lost.
- The seeds are near-duplicates: diff=0 pairs occur (small_1 @5s, small_2 at
  both budgets - two beam seeds return the identical solution) and end values
  repeat across pairs. On large the 2-3 converged optima differ by only 16-38
  of 500 items. The wide beam collapses into ONE basin; there is no diversity
  to recombine.
- Implementation-artifact caveat mostly ruled out: children are re-polished
  with the unchanged `_polish_seed`, so a "weaker child polish" explanation
  does not hold; 9+9 pairs over 10 instances all landing strictly below is not
  a fluke.

## Verdict and family status

- Post-hoc transforms of the converged optimum are dead as a family: relink
  (L20) never produced a child at parent level; H5's perturb loop was a no-op
  on 8/10 pairs with strict acceptance (knowledge/perturb-repolish.md); H7/H8
  polish variants changed nothing. Everything downstream of the polish lands
  on the same fixed point.
- The only mechanism that ever moved objectives after H4 is H5's perturb loop
  on large (+32/+10/+61). Against the FIXED reference, H5's discarded
  candidate is still the best set in hand (fixed-ref mean ~0.999676 vs
  H4/H9 ~0.99966) - see knowledge/perturb-repolish.md for the ratchet math.
- L19 (threshold acceptance + dual-banded ruin) remains UNTESTED and is the
  only direction with demonstrated positive yield; L21/L22 (stronger
  neighborhoods) are untested but bounded by the same single-basin attractor.

## Where the remaining gap lives (@5s, vs reference)

- 100% of the deficit is on 4 instances: large_0 -157, large_1 -77,
  medium_0 -31, medium_1 -15. medium_0/1 gaps are budget-invariant (identical
  at 1s and 5s since H4) and no mechanism has ever moved them.
- Ratio-wise large dominates (class mean 0.9985 vs 0.9996-1.0000 elsewhere).

## What a successor must change

1. Diversify at CONSTRUCTION time, not at the optimum: force the seed pool
   apart (min-distance admission, per-start perturbed duals/orderings), since
   beam_seeds as implemented returns one basin.
2. If recombination is ever retried, only pair genuinely distant optima
   (diff >= ~10% of n), not the near-duplicates the beam currently yields.
3. For the perturb line: threshold acceptance + ruin guidance (L19), with
   early-stop on gap-0 pairs; it is the only positive-yield mechanism observed.
4. The 85-93% idle wall budget is real headroom; spending it inside the
   converged basin (more relinks, more perturb rounds) is proven fruitless -
   spend it on independent trajectories or a stronger exact step instead.
