"""Benchmark definition stub."""

PROBLEM = "<name>"
SENSE = "min"      # "min" (default) or "max" - the framework reads this
SCORER = "auc"     # scorer registry key (autoresearch/scoring.py)

INSTANCE_CLASSES = {
    # "small": {"<param>": ..., "seeds": [0, 1, 2]},
}
TIME_BUDGETS = [1.0, 5.0]
SUBSETS = {
    "smoke": set(),  # a tiny cheap subset, e.g. {"small_0"}
    "full": set(),
}
