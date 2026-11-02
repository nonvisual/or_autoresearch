# Research directions, LLM (mdkp)

<!-- Appended by the Analyst / Researcher agents. One idea per heading:
     "## L<n>: <one line>", free prose below. Combining ideas adds a NEW
     heading that references its sources, e.g. "## L7 (=U2+L3): ...";
     hypotheses derived from the combination reference the new id. -->

## L1: LP-dual surrogate multipliers instead of the 2-point lambda search

Run 20261101T170721Z: the surrogate-ratio greedy's ratio-to-reference predicts
the final ratio almost everywhere (large_0 0.9415 -> 0.9929 is the worst pair),
and the pipeline only ever tries two multiplier vectors (uniform,
residual-tilted) before committing the whole beam to the winner. Solving the
LP relaxation once (even a cheap dual ascent / subgradient on the aggregate
lambda) and using its duals for the item order, the greedy seed, and the bound
geometry should lift large (m=30) where a 2-point search is thinnest, and the
LP optimum also gives a per-instance bound that tells the polish when to stop.

## L2: Order-diverse multi-beam instead of one wide beam at small budgets

Evidence from the same run: 5x width on large_0 (2000 -> 10000 over 2 passes)
bought +48 of a 761 gap and large_1 bought 0, while the 1s runs leave ~48% of
the internal deadline unused. Replacing width growth with K short beams (K=3-4)
under different multiplier vectors, polishing all incumbents, buys order
diversity - the resource the saturation curve says is actually binding.

## L3: Enable drop-1/add-2 polish at the 1s budget

The 1s -> 5s gain is concentrated in medium (+123/+262/+224, mean +0.36%) while
width only moved 12000 -> 16000 and is mostly merged away by dedup; the only
qualitative change at 5s is the `do_pair` gate (budget >= 2.5). Lowering that
gate to ~0.8s with a round/time cap would target medium_1 @1s (0.9920), the
single worst pair of the run, at almost no implementation cost.

## L4: Make budget use monotone (carry incumbents across passes, fix the W//3 split)

At 5s the two-pass schedule made small_0 (37472 -> 37456) and tight_0 (60842 ->
60788) strictly worse than the 1s single wide pass, because pass 1 runs at W//3
and incumbents are not carried forward between passes. Seed every later pass
with the best-so-far solution, and never let the split leave a capped class
(m<=10 hits the 16000 cap) with less effective width than the 1s config had.

## L5: Relaxed-MDD node merges for multi-dimensional per-layer bounds

The truncation score uses one scalar lambda-aggregate fractional-knapsack
bound, which is loosest exactly where the run loses most (m=30). A small
relaxed DD (width k, inexact merges of near-identical remaining-capacity
states) computed alongside the restricted DD gives per-state, per-layer upper
bounds that respect all m dimensions; using those for the width ranking, and
for the restricted DD's state merges, is the standard Bergman-style exact-MDD
recipe and directly attacks the large-class gap.

## L6: Spend the idle 50-80% of the budget on perturbation restarts

Walls are 0.24-0.58s against 0.75-3.75s internal deadlines on every class, and
the polish converges to a single deterministic local optimum. A ruin-and-recreate
loop from the beam incumbents (drop a random-but-seeded subset, re-run insert/swap
until the deadline) is free upside under the current utilization and
monotonically keeps the best solution found.


## L7: Ruin-and-recreate polish for high-dimensional instances
Beam incumbents from a restricted MDD are strong, but 1-0/1-1 and drop-1/add-2 moves cannot cross the wide basins typical of m=30 instances, where near-optimal solutions differ by several items at once. Iterated local search with a deterministic perturbation schedule - remove a fixed-size pseudo-random item subset from an incumbent, greedily repair by surrogate ratio, re-polish with insert/swap, accept equal-or-better - explores a fresh basin per seed while keeping the beam's incumbents as the elite pool. A small fixed schedule (a few perturbation sizes times a few seeds) keeps everything deterministic and inside the same wall-clock cap.

## L8 (=L3+H1 width schedule): restore the wide beam, keep the 0.8s polish gate

H2 (run 20261101T174414Z) proved the 1s polish gate itself works (+9/+67/+105
on medium @1s) but regressed overall because its rebuild cut width to
350/1750 vs H1's 2000-12000/16000 and dropped the refined multiplier: large_1
lost 657 at 1s with the polish adding exactly 0 there. The polish costs 2-20ms
against walls 6-13% of budget, so gate and width are not in conflict - rerun
H1's exact width schedule (W = 3e7*budget/(n*m), cap 16000, refined second
multiplier) with the gate at 0.8s and a hard deadline guard.

## L9: Calibrated anytime width plus polish-until-deadline

Both H1 and H2 pick width from a static formula and then idle (H2 used 13% of
the 1s budget and 6% of the 5s budget; the 350->1750 width bump moved the beam
objective by under 0.35% and was non-monotone on medium_1). Instead, calibrate
the measured per-layer cost on the first pass and keep raising width and
re-beaming from the incumbent pool until 0.75*budget, then loop drop-1/add-2
rounds over ALL incumbents until the deadline instead of a fixed round cap.
Since width past ~350 saturates, the extra time is better spent on repeated
polish restarts from diverse incumbents than on a wider single beam.

## L10: Make the beam prune a total order so width becomes monotone, then spend idle budget on width

H3's large_0 FELL 106892 -> 106752 when width went 2000 (@1s) -> 10000 (@5s):
score ties (integer profits, small-integer residual sums through a fixed lam)
at the argpartition prune boundary are broken arbitrarily, so the top-W state
set is not nested in W. Break ties deterministically (lexsort by score, then
profit desc, then used-vector) to make top-W nested; widening then can never
hurt, and the idle 81-94% of budget can be spent scaling width up safely.

## L11: Round 2 on multipliers - local search over lambda around the LP dual, and measure the uniform-lam beam

Upgrading the second multiplier vector from a residual-tilted heuristic to
HiGHS LP duals was the loop's largest single gain (large 0.9933/0.9948 ->
0.9989/0.9984) while width changes bought nothing, and the residual loss still
grows with m - per-dim multiplier quality is the remaining lever. Perturb the
LP duals (per-dim rescaling, or re-solve with incumbent items fixed), judge
each candidate lambda by a cheap greedy rollout, keep best-of-k beams; log
per-beam objectives so we learn whether the uniform-lam beam ever wins (if
not, its half of the beam work funds the search).

## L12: Anchor the beam at the greedy trajectory so it stops losing to its own seed

H4 diagnostics (run 20261101T190407Z): at m=30 every wide-beam completion ends
101-363 BELOW the plain greedy incumbent (large_0 105543 vs 105753 @1s), while
at m<=10 the beam-only result beats greedy (+124 on medium_0) - the beam never
explores the greedy basin, it competes with it. One change: force the greedy
incumbent's decision sequence through the layers as an additional always-kept
beam state (its per-layer successor states enter the width pool alongside the
surrogate-ranked ones), so the beam refines the strongest known prefix instead
of re-deriving it. Test on large_0/large_1 @1s ratios; guard that m<=10 classes
do not regress (their beam already beats greedy).

## L13 (=L6+L7, re-based on H4 numbers): perturb-and-repolish loop that actually consumes the wall clock

Even at 5s the H4 walls are 0.27-0.41s (6-8% of budget, ~4.6s idle on large),
and polish is the only mechanism still moving the large class (+1245..+2042),
converging in milliseconds to a local optimum of a neighborhood that provably
cannot cross multi-item basins at m=30. One change: after the first polish
converges, loop {remove a fixed-size pseudo-random subset of items from the
incumbent, greedy-repair by surrogate ratio, re-polish, keep best} until
0.6*budget wall deadline, deterministic seeds. Target: large_0/large_1 gaps
(217/174 @1s, 157/77 @5s); success signal is any large-class pair reaching
ratio 1.0 without any m<=10 regression.

## L14 (=L13 successor): threshold acceptance in the perturb loop instead of strict improvement

H5 (run 20261101T194617Z) proved the attractor, not the wall clock, is the
limiter: 8 pairs ran their full round cap (60-300 rounds) with perturb_gain
exactly 0, because strict-improvement-only acceptance plus a uniform 45% ruin
and the same greedy-repair/policy lands every round back on the identical local
optimum. One change to the accept rule: accept the repaired incumbent when
obj >= best - theta (theta ~ 1e-4 of objective, decaying over rounds), track
best separately, and early-stop after K consecutive fruitless rounds. This
turns the same operator into actual basin exploration at identical code cost
and should first move medium_0/medium_1 (flat gaps 31/15, currently zero yield
despite hundreds of rounds), then large.

## L15: LP-dual-guided ruin instead of uniform random 45%

H5's only positive gains came from large (m=30, gaps 77-217), where the H4
diagnosis says the LP-dual scalarization is what degrades - yet the ruin step
still sampled items uniformly, ignoring the price information already computed.
One change: choose the ruined set by dual-price band - remove the items with
worst profit per implied cost on the currently tightest dimensions (residual
capacity per constraint identifies which of the m resources binds), or ruin a
whole price-decile at a time. Perturbing the bottleneck structure rather than
random items changes the repair trajectory, which is the resource H5 exhausted
on large_1 @5s (271 rounds, gain 0, still 77 below reference).

## L16: de-bias keep/discard decisions against the reference ratchet

Each eval is scored against the reference as it stands at that eval's start, and
a candidate that sets a new best gets its score computed against the easier
stale reference while every successor is scored against the updated one. This
flipped the H5 decision: recorded 0.999634 vs H4's 0.999650, but against a
fixed reference H5 is better on all 20 pairs and at both budgets (+2.2e-5 @1s,
+0.9e-5 @5s). One change to the driver/analyst protocol, not the solver: before
discarding a full run whose score is within ~1e-4 of best-so-far, recompute the
incumbent's objectives from its runs/<id>/results.json against the current
reference and compare objective-wise; keep the objective-wise better candidate.
Otherwise the loop systematically punishes successors of record-setting runs and
can stall at a plateau it has already quietly beaten.

## L17: spend the idle wall budget - make the polish phase budget-aware

Both regressing classes in run 20261101T202239Z are time-starved, not
width-starved: the pipeline exits at 0.30s mean wall against the 1.0s budget
(1.22s against 5.0s) with layers_done=N/N everywhere, and the only pairs below
reference are exactly the ones that improve when given more time (medium_2
56096@1s -> 56143@5s closes its whole 47-point gap; large_0 106788 -> 106861,
large_1 107454 -> 107508). H6's restricted-DD prune made this worse by charging
every layer for machinery that never paid there (merges=0 on all 20 pairs,
dominations=0 on medium and large). One change, from the kept H4 pipeline with
the DD prune removed: replace the fixed polish-round count with a loop that
keeps repairing until wall >= 0.8 * budget. Evidence that extra rounds pay on
medium: its 1s objectives sit strictly below its 5s objectives, so the rounds
the clock allows were precisely the missing profit. Caveat from L15: on
large_1 @5s H5 already ran 271 rounds at gain 0, so treat large as upside only
via better seeds, and expect the gain to land on medium_0/medium_1/medium_2
first (=H4-successor, replaces U1 after two negative DD results: H1 and H6).

## L18: strengthen the polish neighborhood itself - bottleneck-aware 2-1 swap and drop-2-add-2

H7 falsified the last round-count idea: polish converges in <= 3 rounds per
seed on every instance and every extra round is a provable no-op
(knowledge/budget-aware-polish.md), so the 57-94% idle wall budget can only be
spent by searching something new - and L13/L14/L15 all kept the same
1-0/1-1/drop-1-add-2 move set. One change: add two multi-item moves, executed
best-improvement after the existing ones, budget-capped as before. (a) 2-1
swap - remove the two incumbent items with the worst profit per unit on the
currently tightest dimensions (residual capacity per constraint identifies the
binding resource), then add the single best free item that fits; (b) drop-2-
add-2 restricted to item pairs whose capacity footprint overlaps the binding
constraint. Targets the flat medium gaps (31/15) that neither 5x width nor
hundreds of perturb rounds touched, then large. Success signal: any objective
gain on medium_0/medium_1 at both budgets, or any large pair moving, with no
m=5 regression from the six gap-0 pairs.

## L19 (=L14+L15): perturb loop seeded from the converged polish optimum with threshold acceptance and dual-banded ruin

H5 proved the attractor is the limiter (271 rounds, gain 0, uniform 45% ruin,
strict-improvement acceptance, every round landing back on the identical local
optimum) and its only positive gains were on large, exactly where the LP-dual
scalarization degrades. Two levers, one candidate: seed from the converged
polish optimum, ruin by dual-price band (remove a decile of items with worst
profit per implied cost on the binding constraints instead of a uniform
subset), greedy-repair by surrogate ratio, accept when obj >= best - theta with
theta decaying from ~1e-4 of the objective over rounds, track best separately,
early-stop after K fruitless rounds, wall cap 0.6*budget. Changing ruin AND
acceptance together is what breaks the return-to-the-same-optimum cycle that
defeated H5; L14 alone or L15 alone leaves the other lever stuck. Success
signal: large_0/large_1 @1s (gaps 217/174) gaining anything, and any
medium_0/medium_1 movement from a mechanism that is not the beam.

## L20: relink the per-seed optima - deterministic crossover of what the pipeline already computes

The kept pipeline runs 2-4 lambda seeds to full polish convergence
(converged=3/3 @1s, 4/4 @5s on all 20 pairs) and then simply stops, leaving
57-94% of the wall budget idle with the seeds' distinct local optima in hand.
One change, cost of a single extra polish (~11ms measured in H7): take the two
best seeds' final solutions, form their symmetric difference, greedy-repair
the union/intersection mix in surrogate-ratio order, re-polish, keep the best
of all incumbents; repeat over seed pairs while wall < 0.8*budget. This is a
second trajectory funded entirely by already-computed artifacts, deterministic,
and it attacks the large class where the seeds are most diverse (m=30 beams
complete far below greedy, so their optima differ most). Success signal: any
objective gain on any pair, since relinking cannot regress below the best
incumbent it starts from.

## L21 (=L18 successor): exhaustive extended-neighborhood descent on the incumbent seed only

H8's log proves move effort on non-incumbent seeds is wasted: medium_0 @5s
shows polish_gain 471 / ext_gain 22 (vs 407/0 @1s) with the objective
bit-identical 57194 at both budgets - the moves improved other seeds and the
best seed absorbed nothing. One change: after the per-seed polish converges,
run the existing extended moves (2-1 swap, drop-2-add-2, plus plain 1-0/1-1)
to full exhaustion on the single best seed - repeated best-improvement descent
until no move applies, looping while wall < 0.8*budget - instead of one sweep
across all seeds. Cost is milliseconds against an 80-91% idle budget, and it
is the only way a stronger neighborhood can touch the reported objective.
Success signal: medium_0 closing its -31 (identical at both budgets since H4)
or large_0's -145/-217 moving; regression guard on the six gap-0 pairs.

## L22 (=L18 successor): LP-dual-composite scoring for drop pairs instead of the binding-dimension heuristic

The drop-2-add-2 filter ranks pairs by footprint overlap on the single
tightest dimension, but the only class with a real remaining gap is large
(m=30), where many constraints are near-binding at once and one-dimensional
tightness mislabels the bottleneck. The pipeline already carries per-constraint
LP duals (lam=lp_duals in every H8 log line), so they are free: score a drop
pair by released shadow price (sum over constraints of dual_i * released_i)
per unit of profit lost, and pick the add pair by minimum dual-weighted cost
among fitting candidates - LP reduced-cost logic instead of the heuristic.
Success signal: ext_gain on large_0/large_1 converting into an actual objective
gain (large_0 -145 @5s is the biggest single gap left), with the absorption
caveat from knowledge/bottleneck-polish-moves.md in mind - pair with L21
scope if ext_gain keeps landing on non-incumbent seeds.

## L23: diversify at construction - force the seed pool apart instead of recombining one basin

H9's logs settle the artifact question: crossover children were re-polished
with the unchanged polish and still ended strictly below the incumbent
(e.g. large_0 @1s ends <= 106723 vs obj 106788), with diff=0 seed pairs on
small and 16-38-of-500 seed gaps on large - the wide beam converges to ONE
basin, so relinking/perturbing its optima cannot pay
(knowledge/relink-seeds.md). Move the diversification upstream instead: run K
independent pipeline starts with deliberately perturbed inputs (LP-dual
scaling jitter per constraint, shuffled greedy tie-breaking, per-start beam
width/order jitter), admit a start's optimum into the pool only if it differs
from every pool member by >= ~5% of n, and spend the idle 85-93% of the wall
budget on those extra starts rather than on post-polish loops. Success
signal: minimum pairwise seed distance an order of magnitude above H9's
5-38 items, and any movement on large_0/large_1 (gaps 157/77 @5s); guard the
six at-reference pairs with the H5-style early-stop.

## L24 (=U1 successor): reduced-cost fixing from the LP duals, then an exact solve of the residual core

Four instances hold 100% of the remaining deficit (large_0 -157, large_1 -77,
medium_0 -31, medium_1 -15 @5s) and the gaps on medium_0/1 have been
budget-invariant through five mechanism changes - a sign the polish family
cannot reach them, while the instances are small enough (n=250-500) for an
exact step. The pipeline already computes LP duals (lam=lp_duals in every
log): fix variables whose LP reduced cost exceeds the integrality gap
bound (obj_LP - incumbent) and run an exact method (B&B or DP over the
residual core) on the few hundred unfixed items to prove or improve the
incumbent. This is the U1 direction re-based: instead of a full relaxed
decision diagram (H6, discarded at 0.999572), use the exact machinery only on
the LP-certified core where the gap is small. Success signal: medium_0/1
closing any part of -31/-15 for the first time, and large_1's -77 shrinking;
a wrong bound shows up as wall overrun, so gate the exact step behind
remaining time and fall back to the incumbent.

## L25 (=L24 successor): discounted rc fixing - trade the certificate for core size

H10 (knowledge/rcfix-exact.md) closed the certified route: with optimal LP
duals and certified gaps of 175-735, no reduced cost qualifies outside m=5
(rc_fix=0, core=full n on medium/large), while the m=5 instances where fixing
works are already at reference. The lever left is the fixing threshold itself:
fix x_j=0 at rc > gamma*(z_LP - incumbent) with gamma ~ 0.25-0.5 (NOT a
certificate), re-polish/greedy-repair from the incumbent restricted to the
surviving core, and unfix on any loss - the incumbent stays feasible and
best-so-far throughout, so the downside is bounded compute, not objective.
The certified variant fixed 0 of 250-500 items; gamma=0.25 should free a
10-30% core on medium, and medium_0/medium_1 (-31/-15, budget-invariant
through six mechanism families) are exactly the instances small enough for
the resulting MIP/DP to finish. Success signal: any movement on medium_0/1 at
either budget with the six at-reference pairs unchanged.

