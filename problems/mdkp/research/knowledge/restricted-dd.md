# Restricted decision diagram inside the beam prune (candidate_restricted_dd.py, H6)

Mechanism (from the candidate source + run 20261101T202239Z stderr): the kept
H4 pipeline (candidate_totalorder_widebeam) with a restricted DD compiled inside
the beam prune. Per layer: exact merge of identical residual resource states
(hash-probed), dominance pruning within a per-layer budgeted scope
(dom_scope, frontier dom_front), then the H4 total-order truncation to width W
(W=2000 on large, 9000 elsewhere). Diagnostics emitted as
`[restricted_dd] n= m= W= dom_scope= dom_front= lam= greedy= beam_seeds= merges= dominations= polish_gain= obj= layers_done= wall=`.

- 2026-11-01, run 20261101T202239Z (full): AUC 0.999572 (1.0s 0.999471,
  5.0s 0.999673), coverage 1.00, all 20 pairs ok, status DISCARDED against the
  kept 0.999650 (H4). reference.json was NOT updated: no pair exceeded its
  reference (reference "updated" stamp is 19:04Z, before the 20:22Z run); max
  ratio is exactly 1.00000. The reported best-so-far 1.0002 is an AUC-curve
  artifact, not a new best objective.
- Per-instance ratios vs reference: small 1.00000 on all 6 pairs; tight 1.00000
  on all 4; medium 0.99946/0.99973/0.99916 (@1s) and 0.99946/0.99973/1.00000
  (@5s); large 0.99797/0.99838 (@1s) and 0.99865/0.99889 (@5s). The DD prune
  HURT medium and large and merely tied H4 on small and tight. Worst pairs:
  large_0@1s 0.99797, large_1@1s 0.99838, large_0@5s 0.99865, medium_2@1s
  0.99916.
- Exact state merging is dead: merges=0 on all 20 full pairs (and 0 on smoke),
  at every class. Residual capacity vectors (m=5..30 dims) are effectively
  unique, so hash-probed exact merges never fire - this replicates H1's MDD
  finding and confirms exact-merge DDs have nothing to compress on these
  instances.
- Dominance pruning fires only where it cannot matter: dominations 48339 total
  on small (6 runs, mean ~8k) and 1368 on tight, but 0 on medium and 0 on large
  (dom_front=8 on large vs 64 elsewhere - the frontier scope collapses exactly
  where the gaps are). Both classes with nonzero dominations scored exactly
  1.00000, i.e. pruned states were refilled by the width truncation anyway.
- The regression mechanism is TIME, not beam content: the DD work charges every
  layer (mean wall 0.62s large, 0.48s medium at 1s) while producing zero merges
  and zero dominations there, and every below-reference pair is time-sensitive:
  medium_2 56096@1s -> 56143@5s (closes its whole gap), large_0 106788 ->
  106861, large_1 107454 -> 107508. The per-layer DD cost shortened the polish
  phase; the beam itself never changed on the regressing classes.
- Verdict on idea U1 (decision diagrams): second negative result after H1. The
  pipeline finishes at 0.30s mean of the 1.0s budget (1.22s of 5.0s) with
  layers_done=N/N everywhere, so neither width nor state dedup is the binding
  constraint - the cheap idle wall budget and the polish round count are (see
  L17). Any DD successor would need lossy/aggregated state merging, for which
  there is no evidence the beam content is the gap.
