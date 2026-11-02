# mdkp research report - loop mdkp__20261101T163710Z (10/10 full iterations)

## Outcome

- Final kept solver: `problems/mdkp/candidates/candidate_totalorder_widebeam.py`
  (hypothesis H4, idea L10), full-subset score **0.999650** (AUC over the
  1 s / 5 s budgets, sense=max), coverage 1.0000.
- The score ratchet: `reference.json` updates whenever any run finds a better
  objective, so late rows are scored against a raised bar (best-so-far line
  1.0002). The six hypotheses after H4 (H5-H10) scored 0.999572-0.999650 and
  were all discarded; none moved a single instance objective.
- No run was killed or infeasible at any point (coverage 1.0000 on every row).

## Final best-known objectives (reference.json at loop end)

| class  | instance | best-known | final run @1s | @5s | ratio @5s | gap @5s |
|--------|----------|-----------:|--------------:|----:|----------:|--------:|
| small  | small_0  |     37472  |        37472  | 37472 | 1.0000 |       0 |
| small  | small_1  |     36538  |        36538  | 36538 | 1.0000 |       0 |
| small  | small_2  |     32260  |        32260  | 32260 | 1.0000 |       0 |
| medium | medium_0 |     57225  |        57194  | 57194 | 0.99946 |    -31 |
| medium | medium_1 |     56549  |        56534  | 56534 | 0.99973 |    -15 |
| medium | medium_2 |     56143  |        56096  | 56143 | 1.0000 |       0 |
| tight  | tight_0  |     60879  |        60879  | 60879 | 1.0000 |       0 |
| tight  | tight_1  |     61400  |        61400  | 61400 | 1.0000 |       0 |
| large  | large_0  |    107005  |       106788  | 106848 | 0.99853 |  -157 |
| large  | large_1  |    107628  |       107454  | 107551 | 0.99910 |    -77 |

Class AUC means (final row): small 1.0000, tight 1.0000, medium 0.9996,
large 0.9985. Mean wall: 0.58 s at the 1 s budget, 3.05 s at 5 s.

## Kept candidates (in order)

1. `example_random.py` - iteration 1 smoke keep (harness shakeout only).
2. `candidate_totalorder_widebeam.py` - the kept best (full row 12). LP-dual
   lambda guidance (picked by greedy profit vs uniform), ratio-sorted layered
   beam with an exact total-order prune and packed tie keys, multi-seed
   best-improvement polish (insert / 1-1 swap / drop-1 add-2), width and
   polish schedules as pure functions of (n, m, budget).

## Idea / hypothesis funnel

| H  | idea | label                          | candidate                         | full score | status    |
|----|------|--------------------------------|-----------------------------------|-----------:|-----------|
| H1 | U1   | MDD beam search                | candidate_dd_beam.py              |   0.997137 | discarded |
| H2 | L3   | 0.8 s polish gate              | candidate_polish1s.py             |   0.995797 | discarded |
| H3 | L8   | width schedule + polish        | candidate_widebeam_polish.py      |   0.999551 | discarded |
| H4 | L10  | total-order wide beam          | candidate_totalorder_widebeam.py  |   0.999650 | KEPT      |
| H5 | L13  | perturb-repolish loop          | candidate_perturb_repolish.py     |   0.999634 | discarded |
| H6 | U1   | restricted DD prune            | candidate_restricted_dd.py        |   0.999572 | discarded |
| H7 | L17  | budget-aware polish loop       | candidate_budgetaware_polish.py   |   0.999586 | discarded |
| H8 | L18  | bottleneck extended moves      | candidate_bottleneck_polish.py    |   0.999592 | discarded |
| H9 | L20  | relink best seeds              | candidate_relink_seeds.py         |   0.999586 | discarded |
| H10| L24  | rc-fix + exact core MIP        | candidate_rcfix_exact.py          |   0.999586 | discarded |

Best score over full rows (row # -> score): 4 -> 0.997137, 7 -> 0.995797,
10 -> 0.999551, 12 -> 0.999650, 15 -> 0.999634, 17 -> 0.999572,
20 -> 0.999586, 22 -> 0.999592, 25 -> 0.999586, 28 -> 0.999586. The peak was
row 12 and was never beaten; the last six rows form a flat plateau one or two
10^-4 below it.

Funnel by idea source: the owner idea U1 (decision diagrams) was tried twice
(H1, H6) and produced the strongest single-lever architecture change but no
kept row; the kept candidate came from the LLM line L10 (beam + total-order
prune), which consolidated earlier LLM ideas L1-L8 (greedy/local-search
baseline, polish gating, width schedule).

## What the last six failures established (distilled knowledge)

1. **One converged basin.** Perturb-repolish (H5), bottleneck-aware extended
   moves (H8) and path relinking between seed optima (H9) all land on
   bit-identical per-instance objectives to the H4 pipeline. The multi-seed
   polish converges to a single attractor; recombination inside it cannot pay.
2. **The idle budget is real but not freely spendable.** 85-93 % of the wall
   budget is idle after the pipeline converges. Spending it on more local
   search of the same neighborhood class yields exactly nothing (H7, H8).
3. **Exact closing needs fixing power the LP duals do not give here.** H10's
   reduced-cost fixing + core MIP (mip_rel_gap=0, warm-started, wall-gated)
   produced exact_gain=0 on all 20 (instance, budget) pairs: rc_fix=0 and a
   full-size core on medium/large (m=10/30), so the MIP just times out
   (81-90 % of wall for nothing), while on m=5 rows it proves optimality only
   where the incumbent was already optimal. The Lagrangian bound meets z_LP to
   ~1e-11, so dual quality is not the issue; the certified gap (664-735 on
   large, 175-222 on medium) simply dwarfs per-item reduced costs.
4. **The deficit structure is budget-invariant and construction-limited.**
   smalls and tights sit at best-known; medium_0 (-31), medium_1 (-15),
   large_0 (-157), large_1 (-77) do not move under any polish, perturb,
   relink or exact mechanism tried. Closing them needs a better construction
   (e.g., a fundamentally stronger bound to steer the beam, or much longer
   budgets), not a better finisher.
5. **Determinism discipline held throughout.** Iteration-count-driven
   schedules with wall clock only as a safety cap, stable/total orders, no
   HiGHS `threads` option (process-global scheduler), and
   accepted-only-if-proven semantics for the exact phase kept every rerun
   bit-identical (verified by double smoke runs on H9 and H10).

## Closing state

Full-row target (10) reached with the H10 eval (run `20261101T215249Z`,
score 0.999586, discarded). Next directions, if the loop resumes: L25 in
`ResearchDirectionsLLM.md` (appended by the final Analyst pass); the
knowledge base entries `relink-seeds`, `bottleneck-polish-moves` and
`rcfix-exact` carry the full verdicts.
