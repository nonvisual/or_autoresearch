"""Print the state digest - the interactive mode's orientation input.

    uv run python scripts/show_digest.py --problem mdkp

Hyperparameters (idea_pivot_n etc.) and the iteration target come from the
repo-root loop.json, so editing that file retunes the interactive loop too.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import digest  # noqa: E402

HYPER_KEYS = ("idea_pivot_n", "new_idea_every_n", "max_hypotheses_per_idea", "plateau_window")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", default=None, help="default: loop.json problem / mdkp")
    args = parser.parse_args()

    cfg = {}
    cfg_path = REPO_ROOT / "loop.json"
    if cfg_path.is_file():
        cfg = json.loads(cfg_path.read_text())
    problem = args.problem or cfg.get("problem", "mdkp")
    target = int(cfg.get("iterations", 15))
    hyper = {k: cfg[k] for k in HYPER_KEYS if k in cfg}

    print(digest.build(REPO_ROOT / "problems" / problem, target, hyper))
    return 0


if __name__ == "__main__":
    sys.exit(main())
