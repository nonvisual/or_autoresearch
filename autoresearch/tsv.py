"""history.tsv: the research log. One row per candidate evaluation.

Columns: iteration, timestamp, candidate_file, score, delta, coverage, subset,
status, hypothesis, hypothesis_id, learnings. ``status`` is ``kept`` or
``discarded``; ``delta`` is the score minus the previous best score; ``subset``
is ``smoke`` or ``full`` - the driver counts only ``full`` rows as iterations
(``full_rows`` / ``count_full`` are the single source for that rule).
``hypothesis_id`` links the row to hypotheses.tsv. Never hand-edit.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = [
    "iteration",
    "timestamp",
    "candidate_file",
    "score",
    "delta",
    "coverage",
    "subset",
    "status",
    "hypothesis",
    "hypothesis_id",
    "learnings",
]

KEPT = "kept"
DISCARDED = "discarded"
FULL = "full"


def path_for(problem_dir: Path) -> Path:
    return problem_dir / "research" / "history.tsv"


def full_rows(rows: list[dict]) -> list[dict]:
    """The rows that count as iterations: one full-subset eval each."""
    return [r for r in rows if r.get("subset") == FULL]


def count_full(problem_dir: Path) -> int:
    rows = read(problem_dir)
    full = full_rows(rows)
    if full or any(r.get("subset") for r in rows):
        return len(full)
    # Legacy files predating the subset column: every row counts as an iteration.
    return len(rows)


def _clean(value) -> str:
    return str(value).replace("\t", " ").replace("\n", " ").strip()


def append(problem_dir: Path, row: dict) -> dict:
    """Append one evaluation row; assigns iteration and timestamp. Returns the row written."""
    path = path_for(problem_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("\t".join(COLUMNS) + "\n")

    existing = read(problem_dir)
    full = {
        "iteration": len(existing) + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidate_file": "",
        "score": "",
        "delta": "",
        "coverage": "",
        "subset": "",
        "status": "",
        "hypothesis": "",
        "hypothesis_id": "",
        "learnings": "",
        **row,
    }
    with path.open("a", newline="") as f:
        f.write("\t".join(_clean(full[c]) for c in COLUMNS) + "\n")
    return full


def read(problem_dir: Path) -> list[dict]:
    path = path_for(problem_dir)
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [dict(r) for r in csv.DictReader(f, delimiter="\t") if any(r.values())]


def best_score(rows: list[dict]) -> float | None:
    """Highest score so far (ratio-to-reference scores are higher-is-better in both senses)."""
    scores = [float(r["score"]) for r in rows if r["score"] != ""]
    return max(scores) if scores else None


def plateau(rows: list[dict], window: int = 4) -> bool:
    """True if no row within the last ``window`` improved on everything before them."""
    if len(rows) < window:
        return False
    prev_best = best_score(rows[:-window])
    recent_best = best_score(rows[-window:])
    if prev_best is None or recent_best is None:
        return False
    return recent_best <= prev_best
