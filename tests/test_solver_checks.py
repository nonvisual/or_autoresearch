"""Solver test battery: contract, feasibility, determinism, budget, bounds."""

from pathlib import Path

from autoresearch import solver_checks

REPO_ROOT = Path(__file__).resolve().parents[1]

OK_SOLVER = (
    "from problems.mdkp.problem import MDKPSolution\n"
    "def solve(instance, time_budget_s):\n"
    "    return MDKPSolution([0])\n"
)

NO_SOLVE = "X = 1\n"

ALL_ITEMS_SOLVER = (
    "from problems.mdkp.problem import MDKPSolution\n"
    "def solve(instance, time_budget_s):\n"
    "    return MDKPSolution(list(range(instance.n)))\n"
)

SLOW_SOLVER = (
    "import time\n"
    "from problems.mdkp.problem import MDKPSolution\n"
    "def solve(instance, time_budget_s):\n"
    "    time.sleep(2.5)\n"
    "    return MDKPSolution([0])\n"
)

# Alternates between two selections across calls via a counter file next to it:
# guaranteed material nondeterminism without timing tricks.
FLAKY_SOLVER = (
    "from pathlib import Path\n"
    "from problems.mdkp.problem import MDKPSolution\n"
    "def solve(instance, time_budget_s):\n"
    "    cnt = Path(__file__).with_suffix('.cnt')\n"
    "    n = int(cnt.read_text()) if cnt.exists() else 0\n"
    "    cnt.write_text(str(n + 1))\n"
    "    return MDKPSolution([n % instance.n])\n"
)


def _status(results, name):
    return next(r.status for r in results if r.name == name)


def test_battery_passes_on_simple_solver(tmp_path):
    solver = tmp_path / "ok.py"
    solver.write_text(OK_SOLVER)
    results = solver_checks.run_battery("mdkp", solver, REPO_ROOT, full=False)
    assert solver_checks.all_pass(results)
    assert _status(results, "contract") == "pass"
    assert _status(results, "feasible") == "pass"
    assert _status(results, "determinism") == "pass"
    assert _status(results, "budget_respect") == "pass"


def test_battery_fails_missing_solve(tmp_path):
    solver = tmp_path / "no_solve.py"
    solver.write_text(NO_SOLVE)
    results = solver_checks.run_battery("mdkp", solver, REPO_ROOT)
    assert _status(results, "contract") == "fail"
    assert not solver_checks.all_pass(results)


def test_battery_fails_infeasible(tmp_path):
    solver = tmp_path / "infeasible.py"
    solver.write_text(ALL_ITEMS_SOLVER)
    results = solver_checks.run_battery("mdkp", solver, REPO_ROOT)
    assert _status(results, "feasible") == "fail"


def test_battery_fails_budget_overrun(tmp_path):
    solver = tmp_path / "slow.py"
    solver.write_text(SLOW_SOLVER)
    results = solver_checks.run_battery("mdkp", solver, REPO_ROOT)
    assert _status(results, "budget_respect") == "fail"


def test_battery_fails_material_nondeterminism(tmp_path):
    solver = tmp_path / "flaky.py"
    solver.write_text(FLAKY_SOLVER)
    results = solver_checks.run_battery("mdkp", solver, REPO_ROOT)
    assert _status(results, "determinism") == "fail"


def test_battery_full_bounds_pass_on_greedy():
    solver = REPO_ROOT / "problems" / "mdkp" / "solvers" / "baseline_greedy.py"
    results = solver_checks.run_battery("mdkp", solver, REPO_ROOT, full=True)
    assert _status(results, "objective_bounds") == "pass"
    assert solver_checks.all_pass(results)


def test_summary_renders_counts(tmp_path):
    solver = tmp_path / "ok.py"
    solver.write_text(OK_SOLVER)
    text = solver_checks.summary(solver_checks.run_battery("mdkp", solver, REPO_ROOT))
    assert "battery:" in text and "pass" in text
