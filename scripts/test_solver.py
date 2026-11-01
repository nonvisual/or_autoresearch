"""CLI over autoresearch/solver_checks.py - the Implementor's fast feedback loop.

    uv run python scripts/test_solver.py --problem mdkp \
        --solver problems/mdkp/candidates/candidate_x.py [--full]

Exit code 0 when nothing failed (warnings acceptable). Run this until green,
then spend the smoke eval.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import solver_checks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", default="mdkp")
    parser.add_argument("--solver", required=True, help="path to a solver .py file")
    parser.add_argument("--full", action="store_true",
                        help="add the objective-bounds check (needs problems/<p>/bounds.py)")
    args = parser.parse_args()

    results = solver_checks.run_battery(args.problem, Path(args.solver), REPO_ROOT, full=args.full)
    print(solver_checks.summary(results))
    return 0 if solver_checks.all_pass(results) else 1


if __name__ == "__main__":
    sys.exit(main())
