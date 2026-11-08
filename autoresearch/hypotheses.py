"""hypotheses.tsv: every hypothesis chosen for experimentation, plus the idea
files' machine contract.

Ideas live in ``research/ResearchDirectionsUser.md`` (human-owned; agents read
but never write it) and ``research/ResearchDirectionsLLM.md`` (agents
append-only). The machine contract is the heading line ``## <id>: <text>``
where ``<id>`` is ``U<n>`` or ``L<n>``. Combining ideas adds a NEW heading
whose text references its sources, e.g. ``## L7 (=U2+L3): ...``; hypotheses
derived from the combination reference the new id. Everything else in those
files is free prose.

hypotheses.tsv columns: id, timestamp, hypothesis, idea_refs, type,
candidate_file, status, score, notes.

- ``idea_refs`` is a SINGLE primary idea id (``U2``, ``L7``) - combinations are
  expressed as new combined idea ids, which keeps the pivot state deterministic.
- ``type`` is ``user`` or ``llm``: whoever authored the driving idea.
- ``status`` moves ``proposed -> running -> kept | discarded``.
- ``notes`` holds the Researcher's one-line rationale for the pick.

Never hand-edit: ``scripts/hypothesis.py`` and ``evaluation/eval_solver.py``
are the only writers.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from autoresearch.tsv import (
    DISCARDED,
    FULL,
    KEPT,
    append_row,
    read_table,
    rewrite_table,
)

COLUMNS = [
    "id",
    "timestamp",
    "hypothesis",
    "idea_refs",
    "type",
    "candidate_file",
    "status",
    "score",
    "notes",
]

PROPOSED = "proposed"
RUNNING = "running"
TERMINAL = {KEPT, DISCARDED}
TYPES = {"user": "user", "llm": "llm"}

IDEA_HEADING_RE = re.compile(r"^##\s*([UL]\d+)((?:\s*\([^)]*\))?)\s*:\s*(.+)$")


def path_for(problem_dir: Path) -> Path:
    return problem_dir / "research" / "hypotheses.tsv"


def user_directions_path(problem_dir: Path) -> Path:
    return problem_dir / "research" / "ResearchDirectionsUser.md"


def llm_directions_path(problem_dir: Path) -> Path:
    return problem_dir / "research" / "ResearchDirectionsLLM.md"


def parse_idea_heads(path: Path) -> list[tuple[str, str]]:
    """(idea_id, one-line text) for every ``## U3: ...`` / ``## L7 (=U2+L3): ...`` heading.

    The combined-idea marker (``(=U2+L3)``) is kept in the text so digests show
    the idea lineage.
    """
    if not path.is_file():
        return []
    heads: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        m = IDEA_HEADING_RE.match(line.strip())
        if m:
            marker = m.group(2).strip()
            text = (marker + " " + m.group(3).strip()).strip() if marker else m.group(3).strip()
            heads.append((m.group(1), text))
    return heads


def append(problem_dir: Path, row: dict) -> dict:
    """Append one hypothesis row; assigns the next H<n> id and status=proposed."""
    existing = read(problem_dir)
    n = 0
    for r in existing:
        m = re.fullmatch(r"H(\d+)", r.get("id", ""))
        if m:
            n = max(n, int(m.group(1)))
    full = {
        "id": f"H{n + 1}",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hypothesis": "",
        "idea_refs": "",
        "type": "",
        "candidate_file": "",
        "status": PROPOSED,
        "score": "",
        "notes": "",
        **row,
    }
    append_row(path_for(problem_dir), COLUMNS, full)
    return full


def read(problem_dir: Path) -> list[dict]:
    return read_table(path_for(problem_dir))


def by_id(problem_dir: Path, hyp_id: str) -> dict | None:
    for r in read(problem_dir):
        if r.get("id") == hyp_id:
            return r
    return None


def set_status(problem_dir: Path, hyp_id: str, status: str, score: str = "",
               fields: dict | None = None) -> dict:
    """Rewrite one row's status (plus score / extra fields). Returns the updated row."""
    rows = read(problem_dir)
    updated = {}
    for r in rows:
        if r.get("id") == hyp_id:
            r["status"] = status
            if score != "":
                r["score"] = score
            if fields:
                r.update(fields)
            updated = r
    if not updated:
        raise KeyError(f"hypothesis {hyp_id} not found")
    rewrite_table(path_for(problem_dir), COLUMNS, rows)
    return updated


def mark_running(problem_dir: Path, hyp_id: str, candidate_file: str) -> dict:
    row = by_id(problem_dir, hyp_id)
    if row is None:
        raise KeyError(f"hypothesis {hyp_id} not found")
    if row["status"] in TERMINAL:
        raise ValueError(f"hypothesis {hyp_id} is already {row['status']}")
    return set_status(problem_dir, hyp_id, RUNNING, fields={"candidate_file": candidate_file})


def resolve_from_history(problem_dir: Path, history_row: dict) -> str | None:
    """Resolve a hypothesis from a full history row (kept/discarded + score).

    Called by eval_solver when it appends a row; only full-subset rows resolve
    hypotheses (smoke runs are development probes, not verdicts). No-op for
    rows without a hypothesis_id or already-terminal hypotheses.
    """
    hyp_id = (history_row.get("hypothesis_id") or "").strip()
    if not hyp_id or history_row.get("subset") != FULL:
        return None
    row = by_id(problem_dir, hyp_id)
    if row is None or row.get("status") in TERMINAL:
        return None
    set_status(
        problem_dir,
        hyp_id,
        history_row.get("status", DISCARDED),
        score=history_row.get("score", ""),
    )
    return hyp_id


def pivot_state(problem_dir: Path, idea_pivot_n: int) -> dict:
    """Deterministic loop state over terminal hypotheses (kept/discarded rows).

    ``current_idea`` is the idea of the latest terminal hypothesis;
    ``consecutive_discards`` counts backwards while the idea stays the same and
    the outcomes stay ``discarded`` (a ``kept`` result resets to 0);
    ``must_pivot`` is True at ``idea_pivot_n`` consecutive discards.
    """
    terminal = [r for r in read(problem_dir) if r.get("status") in TERMINAL]
    state = {"current_idea": None, "consecutive_discards": 0, "must_pivot": False,
             "idea_pivot_n": idea_pivot_n}
    if not terminal:
        return state
    current = terminal[-1].get("idea_refs", "")
    state["current_idea"] = current or None
    n = 0
    for r in reversed(terminal):
        if r.get("idea_refs") != current or r.get("status") != DISCARDED:
            break
        n += 1
    state["consecutive_discards"] = n
    state["must_pivot"] = bool(current) and n >= idea_pivot_n
    return state
