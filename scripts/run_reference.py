"""Phase 1: evaluate every reference solver and build problems/<name>/reference.json.

    uv run python scripts/run_reference.py --problem mdkp --subset full --budgets 1,5,20,60

Refuses to overwrite an existing reference.json (candidates may have improved
it) unless --force is passed. Reference solvers live in problems/<name>/solvers/*.py.
Building the reference with STRONGER budgets than the eval budgets gives the
ratio scores a stable best-known anchor (per-instance improvements then show
up as ratios below 1.0 rather than shifting the scale).
"""

import argparse
import importlib
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import harness, reference, runs, scoring  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", required=True)
    parser.add_argument("--subset", default="full", choices=["smoke", "full"])
    parser.add_argument("--budgets", default=None,
                        help="comma-separated seconds; default benchmark_config.TIME_BUDGETS")
    parser.add_argument("--force", action="store_true", help="rebuild even if reference.json exists")
    args = parser.parse_args()

    problem_dir = REPO_ROOT / "problems" / args.problem
    ref_path = reference.path_for(problem_dir)
    if ref_path.exists() and not args.force:
        print(f"error: {ref_path} already exists; pass --force to rebuild from reference solvers")
        return 2

    solver_files = sorted(p for p in (problem_dir / "solvers").glob("*.py") if p.name != "__init__.py")
    if not solver_files:
        print(f"error: no reference solvers found in {problem_dir / 'solvers'}")
        return 2

    cfg = importlib.import_module(f"problems.{args.problem}.benchmark_config")
    sense = getattr(cfg, "SENSE", scoring.SENSE_MIN)
    budgets = runs.parse_budgets(args.budgets, cfg)
    instances = harness.load_instances(args.problem, args.subset, REPO_ROOT)
    out_dir = runs.new_run_dir(REPO_ROOT)

    best: dict[str, float] = {}
    sources: dict[str, str] = {}
    all_rows: list[dict] = []
    for solver_file in solver_files:
        t0 = time.perf_counter()
        rows = harness.evaluate(args.problem, solver_file, instances, budgets, REPO_ROOT)
        all_rows.extend(rows)
        found = scoring.best_objectives(rows, sense)
        cov = scoring.coverage(rows)
        print(
            f"{solver_file.name}: {len(rows)} runs in {time.perf_counter() - t0:.1f}s | "
            f"coverage {cov:.2f} | best on {len(found)}/{len(instances)} instances"
        )
        for name, obj in found.items():
            if name not in best or scoring.is_better(obj, best[name], sense):
                best[name] = obj
                sources[name] = solver_file.name

    runs.write_json(
        out_dir / "results.json",
        {"problem": args.problem, "subset": args.subset, "rows": all_rows},
    )
    missing = [i.name for i in instances if i.name not in best]
    if missing:
        print(f"error: no reference solver produced a feasible solution for: {missing}")
        print("add a constructive baseline that is always feasible")
        return 1
    reference.build(problem_dir, best, problem=args.problem, sources=sources)
    print(f"wrote {ref_path.relative_to(REPO_ROOT)} from {len(solver_files)} solvers")
    for name in sorted(best):
        print(f"  {name}: {best[name]:.2f} ({sources[name]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
