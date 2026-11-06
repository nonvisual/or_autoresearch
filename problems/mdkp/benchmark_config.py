"""Benchmark definition for mdkp."""

PROBLEM = "mdkp"
SENSE = "max"    # maximization of total profit (framework reads this)
SCORER = "auc"   # default scorer registry key

INSTANCE_CLASSES = {
    # mixed difficulty tiers: n items, m dimensions, correlation, tightness alpha
    "small":  {"n": 100, "m": 5,  "corr": "none",   "alpha": 0.50, "seeds": [0]},  # smoke anchor
    "medium": {"n": 250, "m": 10, "corr": "weak",   "alpha": 0.40, "seeds": [0, 1, 2]},
    "large":  {"n": 500, "m": 30, "corr": "strong", "alpha": 0.35, "seeds": [0, 1]},
    "strong_tight": {"n": 500, "m": 10, "corr": "strong", "alpha": 0.25, "seeds": [0, 1]},
    "xlarge":  {"n": 1000, "m": 30, "corr": "strong", "alpha": 0.35, "seeds": [0, 1]},
    "subsetsum": {"n": 500, "m": 10, "corr": "sum",    "alpha": 0.50, "seeds": [0, 1]},
    "xxlarge":  {"n": 2000, "m": 30, "corr": "strong", "alpha": 0.35, "seeds": [0]},
    "subsetsum_hard": {"n": 1000, "m": 30, "corr": "sum", "alpha": 0.30, "seeds": [0]},
}
# Tier intent: small = MIP-provable well under 1s; medium = LP-guided search pays;
# large = strongly correlated + 30 dims defeats seconds-scale MIP (heuristics shine);
# strong_tight = the classic hard combo (strong correlation + low alpha) that leaves
# real anytime headroom. small/tight classes that solved to exactly 1.0 were removed
# from the full subset - the mean must carry signal, not solved instances.

TIME_BUDGETS = [1.0, 5.0]
# Full eval = 13 instances x 6s budgeted = 78s of solver time (~2.5 min wall
# including 20 subprocess starts). The reference is built with stronger budgets
# (see scripts/run_reference.py --budgets) so ratios measure anytime quality
# against a strong best-known anchor.

SUBSETS = {
    "smoke": {"small_0", "medium_0"},
    "full": {
        "medium_0", "medium_1", "medium_2",
        "large_0", "large_1",
        "strong_tight_0", "strong_tight_1",
        "xlarge_0", "xlarge_1",
        "subsetsum_0", "subsetsum_1",
        "xxlarge_0",
        "subsetsum_hard_0",
    },
}
