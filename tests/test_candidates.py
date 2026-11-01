"""The battery over every committed mdkp solver: a broken candidate fails pytest."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pytest

from autoresearch import solver_checks

_SOLVERS = sorted(
    (REPO_ROOT / "problems" / "mdkp" / "candidates").glob("*.py")
) + sorted((REPO_ROOT / "problems" / "mdkp" / "solvers").glob("*.py"))


@pytest.mark.parametrize("solver", _SOLVERS, ids=lambda p: p.name)
def test_battery(solver):
    results = solver_checks.run_battery("mdkp", solver, REPO_ROOT, full=False)
    fails = [r for r in results if r.status == solver_checks.FAIL]
    assert not fails, f"{solver.name} failed: {[(f.name, f.detail) for f in fails]}"
