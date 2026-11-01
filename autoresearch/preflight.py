"""Fast crash-check before spending an eval on a candidate.

Runs the solver once on the first smoke instance at the smallest configured
budget, through the real harness path (fresh subprocess, budget kill at
budget * SLACK, feasibility check). "Passes preflight" therefore means "the
first harness pair will not crash" - it says nothing about quality.
"""

import importlib
from pathlib import Path

from autoresearch import harness


def run_preflight(problem: str, solver_path: Path, repo_root: Path) -> dict:
    """One cheap (solver, smoke[0], min-budget) run. Returns a harness result row."""
    cfg = importlib.import_module(f"problems.{problem}.benchmark_config")
    inst = harness.load_instances(problem, "smoke", repo_root)[0]
    return harness.run_single(problem, Path(solver_path), inst.path, min(cfg.TIME_BUDGETS), repo_root)


def report(res: dict) -> str:
    status = res.get("status")
    if status == "ok":
        obj = res.get("objective")
        wall = res.get("wall_s", 0.0)
        return f"PREFLIGHT PASS (objective {obj:.2f}, wall {wall:.2f}s)"
    detail = str(res.get("detail") or "").strip()
    tail = "\n".join(detail.splitlines()[-5:])[-400:]
    return f"PREFLIGHT FAIL ({status}): {tail}"
