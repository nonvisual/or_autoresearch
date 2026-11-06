"""Seeded MDKP instance generation, Chu/Beasley-style.

Feasible by construction: the empty selection satisfies every constraint
(capacities are positive). Run as ``python -m problems.mdkp.generator`` to
write ``benchmark/<class>_<seed>.json`` for every configured instance class.

Classes vary n (items), m (dimensions), the value/weight correlation, and the
capacity tightness alpha (capacity_i = floor(alpha * sum_j w_ij)); lower alpha
leaves less room, strongly correlated profits make LP bounds weak.
"""

import json
from pathlib import Path

import numpy as np

from problems.mdkp.benchmark_config import INSTANCE_CLASSES
from problems.mdkp.problem import MDKPInstance

R = 1000  # base range for weights and uncorrelated profits


def make_instance(n: int, m: int, corr: str, alpha: float, seed: int) -> MDKPInstance:
    """Deterministic in (n, m, corr, alpha, seed)."""
    rng = np.random.default_rng(seed)
    W = rng.integers(10, R, size=(m, n))
    wbar = W.mean(axis=0)
    if corr == "none":       # uncorrelated profits
        p = rng.integers(10, R, size=n)
    elif corr == "weak":     # weakly correlated: profit near mean weight
        p = np.round(wbar + rng.integers(-(R // 10), R // 10 + 1, size=n))
    elif corr == "strong":   # strongly correlated: profit = mean weight + R/10
        p = np.round(wbar + R // 10)
    elif corr == "sum":      # subset-sum correlation: profit = total weight (hardest
        p = W.sum(axis=0)    # classic class - LP bound weak, big integrality gap)
    else:
        raise ValueError(f"unknown corr {corr!r} (none | weak | strong | sum)")
    p = np.maximum(p, 1).astype(int)
    c = np.maximum(np.floor(alpha * W.sum(axis=1)).astype(int), 1)
    return MDKPInstance(
        n=n,
        m=m,
        values=[int(v) for v in p],
        weights=[[int(w) for w in row] for row in W],
        capacities=[int(v) for v in c],
    )


def main() -> None:
    bench = Path(__file__).resolve().parent / "benchmark"
    bench.mkdir(exist_ok=True)
    for class_name, params in INSTANCE_CLASSES.items():
        for seed in params["seeds"]:
            inst = make_instance(params["n"], params["m"], params["corr"], params["alpha"], seed)
            (bench / f"{class_name}_{seed}.json").write_text(json.dumps(inst.to_dict()) + "\n")
            print(f"wrote {class_name}_{seed}.json (n={params['n']} m={params['m']})")


if __name__ == "__main__":
    main()
