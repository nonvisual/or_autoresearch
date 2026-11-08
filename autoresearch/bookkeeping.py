"""Driver-side bookkeeping after each session invocation.

Runs after every invocation (all exit paths; the interactive mode calls it via
scripts/finish_iteration.py). Reads the checkpoint ``<ws>/.driver_state.json``
= {"rows_seen": N}, processes history.tsv rows N+1..end, then updates the
checkpoint. Idempotent: re-running with no new rows is a no-op.

Per full row in the batch:
- kept      -> git add candidate + reference.json + research/,
               commit "feat(<problem>): <hypothesis>"
- discarded -> remove the candidate file (only if no kept full row references
               it anywhere), commit "chore(<problem>): discard <candidate> (row #N)"
- no full row -> commit any dirty state under the problem dir as bookkeeping.

research/ now carries hypotheses.tsv, both ResearchDirections files and
knowledge/, so one commit captures the whole iteration's state. If the session
enriched NEITHER ResearchDirectionsLLM.md NOR knowledge/ (git-clean at batch
start), a one-line trace is appended to research/notes/iterations.md before
the commit. Phase 3's report.md gets a "docs:" commit when it appears.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from autoresearch import hypotheses, reference, tsv
from autoresearch.textutil import one_line

STATE_FILE = ".driver_state.json"


def load_state(ws: Path) -> dict:
    path = ws / STATE_FILE
    if path.is_file():
        return {"rows_seen": int(json.loads(path.read_text()).get("rows_seen", 0))}
    return {"rows_seen": 0}


def save_state(ws: Path, state: dict) -> None:
    (ws / STATE_FILE).write_text(json.dumps(state, indent=2) + "\n")


def git(ws: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git in the workspace; clear a stale index.lock and retry once."""
    proc = subprocess.run(
        ["git", "-C", str(ws), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        lock = ws / ".git" / "index.lock"
        if "index.lock" in proc.stderr and lock.exists():
            lock.unlink()
            proc = subprocess.run(
                ["git", "-C", str(ws), *args], capture_output=True, text=True
            )
    return proc


def _dirty(ws: Path, path: Path) -> bool:
    if not path.exists():
        return False
    proc = git(ws, "status", "--porcelain", "--", str(path.relative_to(ws)))
    return bool(proc.stdout.strip())


def _stage_and_commit(ws: Path, paths: list[Path], message: str) -> bool:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return False
    git(ws, "add", *[str(p.relative_to(ws)) for p in existing])
    proc = git(ws, "commit", "-q", "-m", message)
    return proc.returncode == 0


def _research_enriched(ws: Path, problem_dir: Path) -> bool:
    """Did the session write to the LLM idea file or the knowledge base?"""
    return (
        _dirty(ws, hypotheses.llm_directions_path(problem_dir))
        or _dirty(ws, problem_dir / "research" / "knowledge")
    )


def _append_note(notes: Path, row: dict) -> None:
    notes.parent.mkdir(parents=True, exist_ok=True)
    if not notes.exists():
        notes.write_text("# Iteration trace (fallback; sessions usually write richer notes)\n")
    hid = row.get("hypothesis_id") or "-"
    line = (
        f"- #{row.get('iteration', '?')} {hid} {row.get('status', '?')} "
        f"{row.get('score') or '-'} - {one_line(row.get('hypothesis'), 60)}"
    )
    with notes.open("a") as f:
        f.write(line + "\n")


def process(ws: Path, problem: str) -> list[str]:
    """Do bookkeeping for rows added since the checkpoint. Returns actions taken."""
    problem_dir = ws / "problems" / problem
    state = load_state(ws)
    rows = tsv.read(problem_dir)
    if state["rows_seen"] > len(rows):
        # History shrank below the checkpoint (research state reset, branch
        # switch to a shorter line): the checkpoint refers to a past history
        # that no longer exists, so reprocess everything present.
        state["rows_seen"] = 0
    new = rows[state["rows_seen"]:]
    actions: list[str] = []
    research_dir = problem_dir / "research"
    notes = research_dir / "notes" / "iterations.md"
    ref_path = reference.path_for(problem_dir)
    full = tsv.full_rows(new)
    kept_labels = {
        r.get("candidate_file")
        for r in tsv.full_rows(rows)
        if r.get("status") == tsv.KEPT
    }
    enriched = _research_enriched(ws, problem_dir)

    if full:
        total_full = len(tsv.full_rows(rows))
        first_new = total_full - len(full) + 1  # 1-based count of the new batch
        for i, row in enumerate(full, start=first_new):
            label = row.get("candidate_file", "")
            candidate = problem_dir / "candidates" / label
            hypothesis = row.get("hypothesis") or label
            if not enriched:
                _append_note(notes, row)
                actions.append("appended fallback iteration note")
            if row.get("status") == tsv.KEPT:
                ok = _stage_and_commit(
                    ws,
                    [candidate, ref_path, research_dir],
                    f"feat({problem}): {one_line(hypothesis, 72)}",
                )
                if ok:
                    actions.append(f"kept {label} -> feat commit")
            else:
                if label and label not in kept_labels and candidate.exists():
                    git(ws, "rm", "-q", "--ignore-unmatch", str(candidate.relative_to(ws)))
                    candidate.unlink(missing_ok=True)
                ok = _stage_and_commit(
                    ws,
                    [ref_path, research_dir],
                    f"chore({problem}): discard {label} (row #{row.get('iteration', '?')})",
                )
                if ok:
                    actions.append(f"discarded {label} -> chore commit")
    elif new and _dirty(ws, problem_dir):
        ok = _stage_and_commit(
            ws,
            [ref_path, research_dir],
            f"chore({problem}): bookkeeping after incomplete invocation",
        )
        if ok:
            actions.append("incomplete invocation -> bookkeeping commit")

    # The Phase 3 report commits whenever it appears, even with no new rows.
    report = research_dir / "report.md"
    if report.exists() and _dirty(ws, report):
        ok = _stage_and_commit(ws, [report], f"docs({problem}): final report")
        if ok:
            actions.append("report.md -> docs commit")

    if new:
        save_state(ws, {"rows_seen": len(rows)})
    return actions
