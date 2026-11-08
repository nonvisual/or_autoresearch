"""Print the state digest - the interactive mode's orientation input.

    uv run python scripts/show_digest.py --problem mdkp

Hyperparameters (idea_pivot_n etc.) and the iteration target come from the
repo-root loop.json, so editing that file retunes the interactive loop too.
The target is absolute: full rows already complete plus loop.json's
``iterations`` (same arithmetic the driver uses).
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import config, digest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", default=None, help="default: loop.json problem / mdkp")
    args = parser.parse_args()

    cfg = config.read_config(REPO_ROOT) or {}
    problem = args.problem or cfg.get("problem", "mdkp")
    problem_dir = REPO_ROOT / "problems" / problem
    target = config.target_rows(problem_dir, int(cfg.get("iterations", 15)))

    print(digest.build(problem_dir, target, config.hyper_of(cfg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
