"""Trivial candidate: seeded random order + greedy add-while-fits.

Exists only so the evaluation path works from day one. It is expected to lose;
replace it with real candidates during the research loop. Note the fixed seed:
randomness must never come from entropy or the clock, so consecutive
executions produce identical results.
"""

import random

from problems.mdkp.problem import MDKPSolution


def solve(instance, time_budget_s):
    order = list(range(instance.n))
    random.Random(12345).shuffle(order)
    selected: list[int] = []
    used = [0] * instance.m
    for j in order:
        if all(used[i] + instance.weights[i][j] <= instance.capacities[i]
               for i in range(instance.m)):
            selected.append(j)
            for i in range(instance.m):
                used[i] += instance.weights[i][j]
    return MDKPSolution(sorted(selected))
