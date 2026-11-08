"""runs/<UTC ts>/ directories: run ids and archived result files."""

import json
from datetime import datetime, timezone
from pathlib import Path


def new_run_dir(repo_root: Path) -> Path:
    """Create and return a fresh runs/<UTC ts>/ directory."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = repo_root / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


def parse_budgets(cli_value: str | None, cfg) -> list[float]:
    """--budgets flag value over the problem's configured TIME_BUDGETS."""
    if cli_value:
        return [float(b) for b in cli_value.split(",")]
    return [float(b) for b in cfg.TIME_BUDGETS]
