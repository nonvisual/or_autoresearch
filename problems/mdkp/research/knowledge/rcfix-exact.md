# Reduced-cost fixing + exact core MIP tail (candidate_rcfix_exact.py, H10, idea L24)

Mechanism: kept H4 total-order wide-beam pipeline, then one exact phase -
LP relaxation (HiGHS, `_lp_duals`) for z_LP and row duals, fix x_j=0 wherever
the LP reduced cost exceeds the certified gap (z_LP - incumbent), then a core
MIP (HiGHS, mip_rel_gap=0, warm-started with the incumbent,
strict-improvement-only objective cutoff, wall-time-gated). Diagnostics:
`[rcfix_exact] n= m= W= lam= greedy= beam_seeds= polish_gain= obj= z_lp= gap= lag_minus_zlp= rc_fix= core= mip= proved= exact_gain= t_lp= t_beam= t_polish= t_exact= wall=`.

- 2026-11-01, run 20261101T215249Z (full): score 0.999586, coverage 1.00,
  20/20 pairs ok, status DISCARDED against the kept 0.999650 (H4, row 12).
  reference.json was NOT updated: no pair beat its reference (git shows only
  history.tsv/hypotheses.tsv modified); the six at-reference pairs stayed
  exactly at reference.
- The exact phase produced ZERO objective gain anywhere on the full subset
  (exact_gain=0 on all 20 pairs) and proof only where there was nothing to
  gain. Objectives are bit-identical to the kept pipeline's (checked vs run
  20261101T190407Z @1s: large_0 106788, large_1 107454, medium_0 57194,
  medium_2 56096). It was pure dead weight, not a regression.
- Budget consumption was massive: t_exact 0.486s of 0.601s wall @1s (81%) and
  3.78-3.88s of 4.20s @5s (90%) on large/medium, all ending mip=kTimeLimit,
  proved=False. The wall-time gate capped the damage but never left the MIP
  enough time to do anything.
- Fixing power scales inversely with m: rc_fix=0 / core=n on all large (m=30,
  n=500) and all medium (m=10, n=250) pairs; rc_fix=138/132 (core 112/118,
  45-47% of n) on tight_0/1 (m=5); rc_fix=15 (core 85) on small_0 (m=5).
  lag_minus_zlp ~ 1e-11 everywhere, so the duals are optimal - the failure is
  the magnitude of the certified gap, not dual quality: gap 664-735 (large,
  ~0.6% of z_LP), 175-222 (medium), 131-134 (tight), 254 (small_0). No single
  item's LP reduced cost exceeds those gaps outside the m=5 instances.
- Even a 45% core is not solvable in the slice: tight's 112-118-item core with
  mip_rel_gap=0 consumed the whole 3.3-3.9s and proved only on tight_0, where
  the incumbent was already optimal (mip=no_gain). Implied proof throughput is
  ~30-40 core items per second; an exact tail that pays needs a core of
  roughly <= 100 items within a 3-4s slice, i.e. fixing 60-80% of n.
- What would have to change for an exact phase to pay:
  (1) a bound ~4x tighter than the LP (gap must shrink toward the true deficit,
  -15..-157) - Lagrangian/surrogate dual ascent or cut generation, since LP
  duals are already optimal and cannot be squeezed;
  (2) non-certified fixing - fix at a fraction of the certified gap
  (rc > gamma*gap, gamma<1) with an unfix/repair fallback - to reach cores of
  10-20% of n where the certified rule fixes 0;
  (3) a usefulness gate BEFORE starting the MIP (skip when rc_fix=0 or
  core/n > ~0.3) so a hopeless phase costs zero wall time instead of 81-90%;
  (4) an anytime MIP setup (gap target or improvement cutoff) rather than
  mip_rel_gap=0 on a fixed time slice.
- Verdict on L24: negative. The certified rc-fixing route is closed on this
  instance family: where fixing has power (m=5) the beam incumbent is already
  optimal, and where a deficit exists (m=10/30) fixing has no power. The four
  remaining deficits (large_0 -157, large_1 -77, medium_0 -31, medium_1 -15)
  are now untouched by six distinct mechanism families (width, polish gating,
  perturb loops, extended moves, relink, exact tail).
