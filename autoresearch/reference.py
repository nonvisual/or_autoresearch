"""reference.json: best known objective per instance ("best currently known solution").

Phase 1 builds it from reference solvers; the research loop keeps updating it
whenever a candidate finds something better. Score ratios are always computed
against the current state of this file; raw runs stay in runs/<ts>/results.json
so scores remain recomputable under any later reference. Sense-aware: for
maximization problems the "better" comparison is flipped (see
``autoresearch.scoring.is_better``).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from autoresearch.scoring import SENSE_MIN, is_better

FILENAME = "reference.json"


def path_for(problem_dir: Path) -> Path:
    return problem_dir / FILENAME


def load(problem_dir: Path) -> dict | None:
    p = path_for(problem_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def objectives(problem_dir: Path) -> dict[str, float] | None:
    ref = load(problem_dir)
    if ref is None:
        return None
    return {name: entry["objective"] for name, entry in ref["instances"].items()}


def build(
    problem_dir: Path,
    best: dict[str, float],
    problem: str,
    sources: dict[str, str] | None = None,
) -> None:
    """Overwrite reference.json from scratch (phase 1)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sources = sources or {}
    instances = {
        name: {"objective": float(obj), "source": sources.get(name, "unknown")}
        for name, obj in sorted(best.items())
    }
    path_for(problem_dir).write_text(
        json.dumps({"problem": problem, "updated": now, "instances": instances}, indent=2) + "\n"
    )


def update(
    problem_dir: Path,
    found: dict[str, float],
    source: str,
    sense: str = SENSE_MIN,
) -> list[str]:
    """Merge strictly better objectives into reference.json. Returns updated instance names."""
    ref = load(problem_dir)
    if ref is None:
        raise FileNotFoundError(f"{path_for(problem_dir)} missing - run scripts/run_reference.py first")
    changed: list[str] = []
    for name, obj in sorted(found.items()):
        entry = ref["instances"].get(name)
        if entry is None or is_better(obj, entry["objective"], sense):
            ref["instances"][name] = {"objective": float(obj), "source": source}
            changed.append(name)
    if changed:
        ref["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path_for(problem_dir).write_text(json.dumps(ref, indent=2) + "\n")
    return changed
