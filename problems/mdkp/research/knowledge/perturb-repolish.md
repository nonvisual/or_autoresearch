# Ruin-and-recreate perturb stage (candidate_perturb_repolish, H5) - verdict and the reference-ratchet bias

Mechanism: the kept H4 total-order wide-beam pipeline unchanged, plus a final
deterministic loop: ruin 45% of the incumbent (per-round seeded permutation),
greedy-repair in surrogate-ratio order, re-polish with the same move set
(1-0/1-1/drop-1-add-2), accept strict improvements only; cap 60 rounds per
budget second, wall safety at 0.6*budget.

## Run 20261101T194617Z (full): the headline number is misleading

- Recorded score 0.999634 vs H4's 0.999650 -> discarded. BUT H5's objective is
  >= H4's on ALL 20 (instance, budget) pairs (large_0 +32/+10, large_1 +61/+0,
  everything else identical).
- Cause: each eval is scored against the reference as of ITS OWN start. H4's
  full run raised medium_2's reference 56107 -> 56143 and was scored against
  the stale (easier) one; H5 was scored against the updated (harder) one.
  Recomputation: vs a FIXED reference H4 = 0.9995352/0.9997848 (1s/5s), H5 =
  0.9995577/0.9997942 - H5 is genuinely better at both budgets (+2.2e-5,
  +0.9e-5 in mean ratio). The recorded H4 per-budget numbers reproduce exactly
  with medium_2=56107, confirming the mechanism.
- Rule for the loop: when a full-run score lands within ~1e-4 of best-so-far
  and the incumbent's own eval moved any reference, recompute both runs'
  objectives from runs/*/results.json against the current reference before
  discarding. Score deltas across evals are ratchet-biased pessimistic for any
  successor of a reference-setting run.

## Per-pair perturb diagnostics (obj | perturb_gain | rounds | end)

- large_0 @1s: 106820 | 32 | 47/60 | deadline(0.6s)   (H4: 106788)
- large_0 @5s: 106858 | 10 | 242/300 | deadline(3.0s) (H4: 106848)
- large_1 @1s: 107515 | 61 | 44/60 | deadline(0.6s)   (H4: 107454)
- large_1 @5s: 107551 | 0  | 271/300 | deadline(3.0s) (H4: 107551)
- medium_0/1, medium_2 @1s: gain 0, 60/60 end=cap (medium_2 stuck at 56096, gap 47)
- medium_2 @5s: 56143 (= reference), gain 0, 300/300 end=cap
- small_0-2, tight_0-1: at reference already, gain 0, 60 or 300/300 end=cap
- Base pipeline verified bit-identical to H4 (same greedy, polish_gain
  1328/2042/1683/1245 on large), so the diff is purely the perturb stage.

## Mechanism verdict

- perturb_gain > 0 ONLY on large (+32/+10/+61/0 of gaps 157-217/77-174): the
  stage pays exactly where the beam leaves headroom, and yields ~13% of the
  remaining gap. Everywhere the pipeline sits at/near the reference, 300 full
  rounds buy 0.
- end=cap with gain 0 on 8 pairs is the key evidence: uniform 45% ruin +
  surrogate-ratio greedy repair + the same polish is a NO-OP around this
  incumbent - every round lands back on the same local optimum. Strict
  improvement-only acceptance plus a reseeded-per-round ruin means the loop is
  pure resampling around one fixed point, with no diversification memory (no
  threshold/annealing acceptance, no incumbent pool, no crossover).
- The 0.6*budget deadline DOES bind on large (44-47/60 rounds at 1s, 242-271/300
  at 5s), but that is not the limiter: ~2.6 extra seconds on large_0 @5s
  produced +10 total. Per-round yield (~0.05 profit/round-ms) is far too low to
  close 77-147 gaps by more time.
- Cost of the stage elsewhere: cap-ended rounds still burn 1.1-1.2s wall on
  medium @5s for 0 gain (H4 finished that class in 0.32s). Any successor needs
  an early-stop (e.g. stop after K consecutive fruitless rounds).

## What a successor must change (beyond H5)

1. Acceptance: allow equal-or-slightly-worse moves (record-to-record / threshold
   acceptance with theta ~ 1e-4*obj decaying), tracking best separately. Strict
   improvement is what makes 300 rounds a no-op.
2. Ruin guidance: uniform random 45% ignores structure. On large (m=30) the
   LP-dual prices identify which resources bind; ruin by price band (drop the
   items with worst profit-per-implied-cost, or items concentrated on one
   dimension) perturbs the actual bottleneck instead of resampling the same
   repair trajectory.
3. Budget gating: skip the stage entirely when polish_gain == 0 and obj equals
   the reference (small/tight) - it is provably fruitless there.
