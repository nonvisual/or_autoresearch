"""history.tsv: the research log. One row per candidate evaluation.

Columns: iteration, timestamp, candidate_file, score, delta, coverage, subset,
status, hypothesis, hypothesis_id, learnings. ``status`` is ``kept`` or
``discarded``; ``delta`` is the score minus the previous best score; ``subset``
is ``smoke`` or ``full`` - the driver counts only ``full`` rows as iterations
(``full_rows`` / ``count_full`` are the single source for that rule).
``hypothesis_id`` links the row to hypotheses.tsv. Never hand-edit.

Also hosts the generic TSV table helpers (read/append/rewrite) shared with
hypotheses.tsv.
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


def _clean(value) -> str:
    return str(value).replace("\t", " ").replace("\n", " ").strip()


def read_table(path: Path) -> list[dict]:
    """Generic TSV read: dict rows, blank lines skipped."""
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [dict(r) for r in csv.DictReader(f, delimiter="\t") if any(r.values())]


def append_row(path: Path, columns: list[str], row: dict) -> None:
    """Append one filled-in row; writes the header first when the file is new."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("\t".join(columns) + "\n")
    with path.open("a", newline="") as f:
        f.write("\t".join(_clean(row[c]) for c in columns) + "\n")


def rewrite_table(path: Path, columns: list[str], rows: list[dict]) -> None:
    """Full rewrite (header + rows) - for in-place row updates."""
    with path.open("w", newline="") as f:
        f.write("\t".join(columns) + "\n")
        for r in rows:
            f.write("\t".join(_clean(r[c]) for c in columns) + "\n")


def full_rows(rows: list[dict]) -> list[dict]:
    """The rows that count as iterations: one full-subset eval each."""
    return [r for r in rows if r.get("subset") == FULL]


def count_full(problem_dir: Path) -> int:
    rows = read(problem_dir)
    full = full_rows(rows)
    if any(r.get("subset") for r in rows):
        return len(full)
    # Legacy files predating the subset column: every row counts as an iteration.
    return len(rows)


def append(problem_dir: Path, row: dict, existing: list[dict] | None = None) -> dict:
    """Append one evaluation row; assigns iteration and timestamp. Returns the row written.

    ``existing``: the already-read rows of this table (saves a re-read when the
    caller just loaded them, e.g. eval_solver for prev_best).
    """
    existing = read(problem_dir) if existing is None else existing
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
    append_row(path_for(problem_dir), COLUMNS, full)
    return full


def read(problem_dir: Path) -> list[dict]:
    return read_table(path_for(problem_dir))


def best_score(rows: list[dict]) -> float | None:
    """Highest score so far (ratio-to-reference scores are higher-is-better in both senses)."""
    best = best_row(rows)
    return float(best["score"]) if best else None


def best_row(rows: list[dict]) -> dict | None:
    """The row with the highest non-empty score (callers pre-filter to full rows)."""
    scored = [r for r in rows if r.get("score") != ""]
    return max(scored, key=lambda r: float(r["score"])) if scored else None
