"""Reference solver: surrogate-ratio greedy - the always-feasible anchor.

Orders items by profit over the tightest normalized resource usage
(``p_j / max_i w_ij / c_i``) and adds each item if it fits in every dimension.
Fast (milliseconds at n=500) and always feasible, so reference.json gets a
finite value on every instance. Weak on its own: exactly what the research
loop is expected to improve upon first.
"""

import numpy as np

from problems.mdkp.problem import MDKPSolution


def solve(instance, time_budget_s):
    caps = np.asarray(instance.capacities, dtype=float)
    weights = np.asarray(instance.weights, dtype=float)      # (m, n)
    values = np.asarray(instance.values, dtype=float)        # (n,)

    usage = (weights / caps[:, None]).max(axis=0)            # tightest-dimension load per item
    keys = values / np.maximum(usage, 1e-12)
    order = np.argsort(-keys, kind="stable")                 # deterministic tie-breaks

    remaining = caps.copy()
    selected: list[int] = []
    for j in order:
        w = weights[:, j]
        if np.all(w <= remaining):
            remaining -= w
            selected.append(int(j))
    return MDKPSolution(sorted(selected))
