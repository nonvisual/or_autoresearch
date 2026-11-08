"""mdkp problem package: generator, evaluator, brute-force checks, baselines."""

import itertools
import math

import numpy as np
import pytest

from problems.mdkp.bounds import bound as lp_bound
from problems.mdkp.evaluator import check_feasible, objective
from problems.mdkp.generator import make_instance
from problems.mdkp.problem import MDKPInstance, MDKPSolution


def test_generator_is_deterministic():
    a = make_instance(40, 3, "weak", 0.4, 7).to_dict()
    b = make_instance(40, 3, "weak", 0.4, 7).to_dict()
    assert a == b
    c = make_instance(40, 3, "weak", 0.4, 8).to_dict()
    assert a != c  # different seed differs


def test_generator_shapes_and_capacity_formula():
    inst = make_instance(50, 4, "none", 0.35, 0)
    assert inst.n == 50 and inst.m == 4
    assert len(inst.values) == 50
    assert len(inst.weights) == 4 and all(len(row) == 50 for row in inst.weights)
    for i in range(4):
        expected = max(int(math.floor(0.35 * sum(inst.weights[i]))), 1)
        assert inst.capacities[i] == expected
    assert all(v >= 1 for v in inst.values)
    assert all(w >= 10 for row in inst.weights for w in row)


def test_generator_subset_sum_mode():
    inst = make_instance(40, 4, "sum", 0.5, 3)
    W = np.asarray(inst.weights)
    assert inst.values == [int(v) for v in W.sum(axis=0)]  # profit = total weight
    with pytest.raises(ValueError):
        make_instance(10, 2, "bogus", 0.5, 0)


def test_instance_json_roundtrip():
    inst = make_instance(20, 2, "strong", 0.5, 1)
    clone = MDKPInstance.from_dict(inst.to_dict())
    assert clone == inst


def test_instance_from_dict_rejects_bad_shapes():
    d = make_instance(10, 2, "none", 0.5, 0).to_dict()
    d["values"] = d["values"][:-1]
    with pytest.raises(ValueError):
        MDKPInstance.from_dict(d)


def test_evaluator_accepts_valid_rejects_invalid():
    inst = make_instance(30, 3, "none", 0.4, 2)
    assert check_feasible(inst, MDKPSolution([]))            # empty is feasible
    assert check_feasible(inst, MDKPSolution([0, 5, 29]))
    assert not check_feasible(inst, MDKPSolution([0, 0]))    # duplicate
    assert not check_feasible(inst, MDKPSolution([0, 30]))   # out of range
    assert not check_feasible(inst, MDKPSolution(list(range(30))))  # over capacity


def test_objective_matches_brute_force_optimum():
    inst = make_instance(14, 2, "weak", 0.4, 5)
    best_v, best_s = -1.0, []
    for mask in range(1 << inst.n):
        sel = [j for j in range(inst.n) if mask >> j & 1]
        if check_feasible(inst, MDKPSolution(sel)):
            v = sum(inst.values[j] for j in sel)
            if v > best_v:
                best_v, best_s = v, sel
    assert objective(inst, MDKPSolution(best_s)) == pytest.approx(best_v)


def test_baseline_mip_matches_brute_force_on_tiny_instance():
    from problems.mdkp.solvers.baseline_mip import solve as mip_solve

    inst = make_instance(13, 2, "weak", 0.45, 9)
    best_v = -1.0
    for mask in range(1 << inst.n):
        sel = [j for j in range(inst.n) if mask >> j & 1]
        if check_feasible(inst, MDKPSolution(sel)):
            best_v = max(best_v, sum(inst.values[j] for j in sel))
    sol = mip_solve(inst, 5.0)
    assert check_feasible(inst, sol)
    assert objective(inst, sol) == pytest.approx(best_v)  # exact optimum


def test_lp_bound_dominates_mip_optimum():
    from problems.mdkp.solvers.baseline_mip import solve as mip_solve

    inst = make_instance(40, 5, "weak", 0.4, 11)
    sol = mip_solve(inst, 3.0)
    assert objective(inst, sol) <= lp_bound(inst) * (1 + 1e-6)


def test_baseline_greedy_always_feasible_and_sane():
    from problems.mdkp.solvers.baseline_greedy import solve as greedy_solve
    from problems.mdkp.solvers.baseline_mip import solve as mip_solve

    for cls_args, seed in [((60, 3, "none", 0.5), 0), ((80, 6, "weak", 0.25), 1),
                           ((100, 2, "strong", 0.35), 2)]:
        inst = make_instance(*cls_args, seed)
        sol = greedy_solve(inst, 1.0)
        assert check_feasible(inst, sol)
        assert objective(inst, sol) >= 0.0
        mip = mip_solve(inst, 1.0)
        assert check_feasible(inst, mip)
        assert objective(inst, sol) <= objective(inst, mip) * (1 + 1e-9)  # greedy <= MIP


def test_example_random_is_feasible_and_deterministic():
    from problems.mdkp.candidates.example_random import solve as random_solve

    inst = make_instance(50, 4, "none", 0.3, 4)
    a = random_solve(inst, 1.0)
    b = random_solve(inst, 1.0)
    assert check_feasible(inst, a)
    assert a.to_dict() == b.to_dict()  # fixed seed -> identical reruns
