"""Preflight: the free crash-check gate before any eval spend."""

import json
from pathlib import Path

from autoresearch import preflight

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_solver(tmp_path, body, name="solver.py"):
    path = tmp_path / name
    path.write_text(body)
    return path


def test_preflight_passes_on_example_random():
    res = preflight.run_preflight(
        "mdkp", REPO_ROOT / "problems" / "mdkp" / "candidates" / "example_random.py", REPO_ROOT
    )
    assert res["status"] == "ok"
    assert "PREFLIGHT PASS" in preflight.report(res)


def test_preflight_catches_import_crash(tmp_path):
    solver = _write_solver(tmp_path, "import does_not_exist_anywhere\n")
    res = preflight.run_preflight("mdkp", solver, REPO_ROOT)
    assert res["status"] == "error"
    assert "PREFLIGHT FAIL (error)" in preflight.report(res)


def test_preflight_catches_solve_crash(tmp_path):
    solver = _write_solver(
        tmp_path,
        "def solve(instance, time_budget_s):\n    raise RuntimeError('kaputt')\n",
    )
    res = preflight.run_preflight("mdkp", solver, REPO_ROOT)
    assert res["status"] == "error"
    assert "kaputt" in preflight.report(res)


def test_preflight_catches_infeasible(tmp_path):
    solver = _write_solver(
        tmp_path,
        "from problems.mdkp.problem import MDKPSolution\n"
        "def solve(instance, time_budget_s):\n"
        "    return MDKPSolution(list(range(instance.n)))\n",
    )
    res = preflight.run_preflight("mdkp", solver, REPO_ROOT)
    assert res["status"] == "infeasible"
    assert "PREFLIGHT FAIL (infeasible)" in preflight.report(res)
