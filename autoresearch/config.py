"""loop.json: shared loading plus the hyperparameters the digest renders."""

import json
import sys
from pathlib import Path

from autoresearch import tsv

# Loop hyperparameters rendered in the digest (subset of loop.json keys).
HYPER_KEYS = ("idea_pivot_n", "max_hypotheses_per_idea", "new_idea_every_n")


def read_config(root: Path) -> dict | None:
    """Parsed loop.json, or None when the repo has none."""
    path = root / "loop.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def load_config(root: Path) -> dict:
    """loop.json or exit(2) - the driver refuses to run without it."""
    cfg = read_config(root)
    if cfg is None:
        print(f"error: {root / 'loop.json'} missing")
        sys.exit(2)
    return cfg


def hyper_of(cfg: dict) -> dict:
    return {k: cfg[k] for k in HYPER_KEYS if k in cfg}


def target_rows(problem_dir: Path, iterations: int) -> int:
    """Absolute full-row target: rows already complete plus the planned iterations."""
    return tsv.count_full(problem_dir) + iterations
