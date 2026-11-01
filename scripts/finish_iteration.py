"""CLI wrapper: run driver bookkeeping manually.

    uv run python scripts/finish_iteration.py --workspace loop_runs/<ws> --problem mdkp
    uv run python scripts/finish_iteration.py                 # interactive mode: repo root

The logic lives in autoresearch/bookkeeping.py; scripts/run_loop.py calls it
in-process after every invocation. The interactive /or-iterate skill runs this
after each full iteration instead (there is no driver to do it).
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import bookkeeping  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=None,
                        help="workspace root; default the repo root (interactive mode)")
    parser.add_argument("--problem", default="mdkp")
    args = parser.parse_args()

    ws = Path(args.workspace).resolve() if args.workspace else REPO_ROOT
    actions = bookkeeping.process(ws, args.problem)
    for a in actions:
        print(f"[finish_iteration] {a}")
    if not actions:
        print("[finish_iteration] nothing to do (no new rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
