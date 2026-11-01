"""Child-process entry point: run one solver on one instance under one budget.

Invoked by the harness as::

    python -m autoresearch.run_solver --problem mdkp --solver /path/to/solver.py \
        --instance /path/to/instance.json --budget 5.0

Prints exactly one JSON object on stdout::

    {"status": "ok", "objective": 123.4, "solution": {...}}

Overruns are not handled here - the harness kills this process at budget * SLACK.
Solvers may emit diagnostics on stderr; the harness archives them per run.
"""

import argparse
import importlib
import importlib.util
import json
import sys
import traceback
from pathlib import Path

from autoresearch.spec import SolverContractError


def load_solver_module(solver_path: str):
    stem = Path(solver_path).stem.replace("-", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(f"candidate_{stem}", solver_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load solver from {solver_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "solve"):
        raise SolverContractError(f"{solver_path} does not define solve(instance, time_budget_s)")
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", required=True)
    parser.add_argument("--solver", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    payload = {"status": "error", "objective": None, "solution": None, "detail": ""}
    try:
        problem_mod = importlib.import_module(f"problems.{args.problem}.problem")
        evaluator = importlib.import_module(f"problems.{args.problem}.evaluator")

        raw = json.loads(Path(args.instance).read_text())
        instance = problem_mod.Instance.from_dict(raw)

        solver = load_solver_module(args.solver)
        solution = solver.solve(instance, args.budget)

        if not evaluator.check_feasible(instance, solution):
            payload = {
                "status": "infeasible",
                "objective": None,
                "solution": solution.to_dict() if hasattr(solution, "to_dict") else None,
                "detail": "solver returned an infeasible solution",
            }
        else:
            payload = {
                "status": "ok",
                "objective": float(evaluator.objective(instance, solution)),
                "solution": solution.to_dict(),
                "detail": "",
            }
    except Exception:
        payload = {
            "status": "error",
            "objective": None,
            "solution": None,
            "detail": traceback.format_exc()[-4000:],
        }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
