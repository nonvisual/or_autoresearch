"""hypotheses.tsv machinery: ids, transitions, resolution, pivot state, CLI."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pytest

from autoresearch import hypotheses


def _add(problem_dir, idea, hyp="some hypothesis", type_="llm"):
    return hypotheses.append(problem_dir, {
        "hypothesis": hyp, "idea_refs": idea, "type": type_, "notes": "rationale",
    })


def test_append_assigns_sequential_ids(tmp_path):
    first = _add(tmp_path, "U1", type_="user")
    second = _add(tmp_path, "L2")
    assert first["id"] == "H1" and first["status"] == "proposed"
    assert second["id"] == "H2"


def test_mark_running_then_terminal(tmp_path):
    _add(tmp_path, "U1")
    row = hypotheses.mark_running(tmp_path, "H1", "candidate_x.py")
    assert row["status"] == "running"
    assert row["candidate_file"] == "candidate_x.py"
    hypotheses.set_status(tmp_path, "H1", "kept", score="1.05")
    with pytest.raises(ValueError):
        hypotheses.mark_running(tmp_path, "H1", "candidate_y.py")  # already terminal
    assert hypotheses.by_id(tmp_path, "H1")["score"] == "1.05"
    with pytest.raises(KeyError):
        hypotheses.set_status(tmp_path, "H9", "kept")


def test_resolve_from_history_full_row_only(tmp_path):
    _add(tmp_path, "L1")
    hypotheses.mark_running(tmp_path, "H1", "candidate_x.py")
    out = hypotheses.resolve_from_history(tmp_path, {
        "subset": "smoke", "status": "kept", "score": "1.0", "hypothesis_id": "H1",
    })
    assert out is None  # smoke rows never resolve
    out = hypotheses.resolve_from_history(tmp_path, {
        "subset": "full", "status": "discarded", "score": "0.9", "hypothesis_id": "H1",
    })
    assert out == "H1"
    assert hypotheses.by_id(tmp_path, "H1")["status"] == "discarded"
    # idempotent on already-terminal ids
    assert hypotheses.resolve_from_history(tmp_path, {
        "subset": "full", "status": "kept", "score": "1.0", "hypothesis_id": "H1",
    }) is None


def test_pivot_state_rules(tmp_path):
    assert hypotheses.pivot_state(tmp_path, 3)["current_idea"] is None  # empty state
    for _ in range(2):
        h = _add(tmp_path, "L1")
        hypotheses.set_status(tmp_path, h["id"], "discarded")
    st = hypotheses.pivot_state(tmp_path, 3)
    assert st["current_idea"] == "L1" and st["consecutive_discards"] == 2
    assert not st["must_pivot"]
    h = _add(tmp_path, "L1")
    hypotheses.set_status(tmp_path, h["id"], "discarded")
    st = hypotheses.pivot_state(tmp_path, 3)
    assert st["consecutive_discards"] == 3 and st["must_pivot"]
    h = _add(tmp_path, "L1")
    hypotheses.set_status(tmp_path, h["id"], "kept", score="1.1")
    st = hypotheses.pivot_state(tmp_path, 3)
    assert st["consecutive_discards"] == 0 and not st["must_pivot"]  # kept resets
    h = _add(tmp_path, "U2")
    hypotheses.set_status(tmp_path, h["id"], "discarded")
    st = hypotheses.pivot_state(tmp_path, 3)
    assert st["current_idea"] == "U2" and st["consecutive_discards"] == 1  # idea switch resets


def test_parse_idea_heads_incl_combined(tmp_path):
    user = tmp_path / "ResearchDirectionsUser.md"
    user.write_text(
        "# directions\n\n## U1: first idea\nprose\n\n## U2: second idea\n"
    )
    llm = tmp_path / "ResearchDirectionsLLM.md"
    llm.write_text(
        "# llm\n\n## L3: third\n## L7 (=U2+L3): combined idea\nprose\n"
    )
    assert [i for i, _ in hypotheses.parse_idea_heads(user)] == ["U1", "U2"]
    heads = hypotheses.parse_idea_heads(llm)
    assert [i for i, _ in heads] == ["L3", "L7"]
    assert heads[1][1] == "(=U2+L3) combined idea"  # marker kept for lineage


def test_cli_add_start_list(tmp_path, capsys, monkeypatch):
    import scripts.hypothesis as cli

    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    problem_dir = tmp_path / "problems" / "mdkp"
    problem_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "sys.argv",
        ["hypothesis.py", "add", "--problem", "mdkp", "--hypothesis", "dual greedy",
         "--idea-ref", "U1", "--type", "user", "--notes", "try LP duals"],
    )
    assert cli.main() == 0
    monkeypatch.setattr(
        "sys.argv",
        ["hypothesis.py", "start", "--problem", "mdkp", "--id", "H1",
         "--candidate", "candidate_dual.py"],
    )
    assert cli.main() == 0
    rows = hypotheses.read(problem_dir)
    assert rows[0]["status"] == "running"
    assert rows[0]["candidate_file"] == "candidate_dual.py"
