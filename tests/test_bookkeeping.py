"""Bookkeeping against a real git repo in tmp: commits, discards, fallback notes."""

import subprocess
from pathlib import Path

from autoresearch import bookkeeping, hypotheses, tsv


def _git(ws: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(ws), *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _make_ws(tmp_path: Path, make_git_repo) -> Path:
    ws = tmp_path / "ws"
    problem_dir = ws / "problems" / "mdkp"
    (problem_dir / "candidates").mkdir(parents=True)
    (problem_dir / "research").mkdir(parents=True)
    (ws / "README.md").write_text("# ws\n")  # something to commit at init
    make_git_repo(ws)
    return ws


def _full_row(problem_dir: Path, label: str, status: str, hid: str = "H1") -> None:
    tsv.append(problem_dir, {
        "candidate_file": label, "score": "1.0", "delta": "0.0", "coverage": "1.0",
        "subset": "full", "status": status, "hypothesis": f"hyp for {label}",
        "hypothesis_id": hid, "learnings": "none",
    })


def test_kept_row_commits_research_state_incl_hypotheses_and_knowledge(tmp_path, make_git_repo):
    ws = _make_ws(tmp_path, make_git_repo)
    problem_dir = ws / "problems" / "mdkp"
    candidate = problem_dir / "candidates" / "candidate_x.py"
    candidate.write_text("# candidate\n")
    knowledge = problem_dir / "research" / "knowledge"
    knowledge.mkdir(parents=True, exist_ok=True)
    (knowledge / "topic.md").write_text("# Topic\n- learning\n")
    hypotheses.append(problem_dir, {"hypothesis": "hyp", "idea_refs": "U1", "type": "user"})
    _full_row(problem_dir, "candidate_x.py", "kept")

    actions = bookkeeping.process(ws, "mdkp")
    assert any("feat commit" in a for a in actions)
    head = _git(ws, "show", "--stat", "--name-only", "HEAD")
    assert "problems/mdkp/research/hypotheses.tsv" in head
    assert "problems/mdkp/research/knowledge/topic.md" in head
    assert "problems/mdkp/candidates/candidate_x.py" in head


def test_discarded_row_removes_candidate_with_guard(tmp_path, make_git_repo):
    ws = _make_ws(tmp_path, make_git_repo)
    problem_dir = ws / "problems" / "mdkp"
    candidate = problem_dir / "candidates" / "candidate_x.py"
    candidate.write_text("# candidate\n")
    _full_row(problem_dir, "candidate_x.py", "kept")  # a kept row references it
    bookkeeping.process(ws, "mdkp")

    _full_row(problem_dir, "candidate_x.py", "discarded", hid="H2")
    bookkeeping.process(ws, "mdkp")
    assert candidate.exists()  # kept somewhere: not removed

    _full_row(problem_dir, "candidate_y.py", "discarded", hid="H3")
    (problem_dir / "candidates" / "candidate_y.py").write_text("# y\n")
    bookkeeping.process(ws, "mdkp")
    assert not (problem_dir / "candidates" / "candidate_y.py").exists()  # unreferenced: removed


def test_fallback_note_when_session_did_not_enrich(tmp_path, make_git_repo):
    ws = _make_ws(tmp_path, make_git_repo)
    problem_dir = ws / "problems" / "mdkp"
    _full_row(problem_dir, "candidate_x.py", "discarded")
    bookkeeping.process(ws, "mdkp")
    notes = problem_dir / "research" / "notes" / "iterations.md"
    assert notes.exists()
    assert "discarded" in notes.read_text()


def test_stale_checkpoint_after_history_reset_is_reprocessed(tmp_path, make_git_repo):
    ws = _make_ws(tmp_path, make_git_repo)
    problem_dir = ws / "problems" / "mdkp"
    candidate = problem_dir / "candidates" / "candidate_x.py"
    candidate.write_text("# candidate\n")
    _full_row(problem_dir, "candidate_x.py", "kept")
    # checkpoint from a LONGER past history (e.g. before a research-state
    # reset): rows_seen must not swallow the rows that exist now
    bookkeeping.save_state(ws, {"rows_seen": 41})
    actions = bookkeeping.process(ws, "mdkp")
    assert any("feat commit" in a for a in actions)  # row processed despite stale checkpoint
    assert bookkeeping.load_state(ws) == {"rows_seen": 1}


def test_no_fallback_note_when_session_enriched(tmp_path, make_git_repo):
    ws = _make_ws(tmp_path, make_git_repo)
    problem_dir = ws / "problems" / "mdkp"
    _full_row(problem_dir, "candidate_x.py", "discarded")
    # the "session" appended an LLM idea after the row was written
    llm = hypotheses.llm_directions_path(problem_dir)
    llm.write_text("# llm\n\n## L1: new idea\n")
    bookkeeping.process(ws, "mdkp")
    notes = problem_dir / "research" / "notes" / "iterations.md"
    assert not notes.exists()


def test_incomplete_invocation_commits_dirty_state(tmp_path, make_git_repo):
    ws = _make_ws(tmp_path, make_git_repo)
    problem_dir = ws / "problems" / "mdkp"
    tsv.append(problem_dir, {
        "candidate_file": "c.py", "score": "0.5", "subset": "smoke", "status": "discarded",
        "coverage": "1.0", "delta": "", "hypothesis": "", "hypothesis_id": "", "learnings": "",
    })
    actions = bookkeeping.process(ws, "mdkp")
    assert any("incomplete invocation" in a for a in actions)


def test_idempotent_and_report_commit(tmp_path, make_git_repo):
    ws = _make_ws(tmp_path, make_git_repo)
    problem_dir = ws / "problems" / "mdkp"
    _full_row(problem_dir, "candidate_x.py", "kept")
    bookkeeping.process(ws, "mdkp")
    assert bookkeeping.process(ws, "mdkp") == []  # nothing new -> no-op

    report = problem_dir / "research" / "report.md"
    report.write_text("# Final report\n")
    actions = bookkeeping.process(ws, "mdkp")
    assert any("docs commit" in a for a in actions)
    assert "docs(mdkp)" in _git(ws, "log", "--oneline")
