"""Scaffold a new problem package from problems/_template.

    uv run python scripts/new_problem.py --name binpacking
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="problem package name (snake_case)")
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.name):
        print("error: --name must be snake_case (letters, digits, underscores)")
        return 2
    src = REPO_ROOT / "problems" / "_template"
    dst = REPO_ROOT / "problems" / args.name
    if dst.exists():
        print(f"error: {dst} already exists")
        return 2

    shutil.copytree(src, dst)
    print(f"scaffolded {dst.relative_to(REPO_ROOT)}")
    print("next steps:")
    print(f"  1. implement problem.py, generator.py, evaluator.py, benchmark_config.py (see {dst / 'README.md'})")
    print(f"     - benchmark_config.py: set SENSE ('min' or 'max') and optionally SCORER")
    print(f"  2. implement solvers/baseline_strong.py and solvers/baseline_constructive.py")
    print(f"     (at least one must be feasible on every instance)")
    print(f"  3. optional: bounds.py (bound(instance) for the battery --full check), scorers.py (custom scorers)")
    print(f"  4. uv run python -m problems.{args.name}.generator")
    print(f"  5. uv run python scripts/run_reference.py --problem {args.name} --subset full"
          " --budgets <stronger than TIME_BUDGETS>")
    print(f"  6. point loop.json 'problem' at '{args.name}' and start the loop - see AGENTS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
