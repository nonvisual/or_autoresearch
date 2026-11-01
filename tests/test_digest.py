"""Digest v2: idea heads, pivot rendering, hypothesis tail, knowledge tail, bounds."""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from autoresearch import digest, hypotheses, reference, tsv


def _seed(problem_dir: Path) -> None:
    (problem_dir / "research").mkdir(parents=True, exist_ok=True)
    reference.build(problem_dir, {"small_0": 100.0, "medium_0": 200.0}, problem="mdkp")
    hypotheses.user_directions_path(problem_dir).write_text(
        "# directions\n\n## U1: LP-guided priorities\nprose\n\n## U2: local search\n"
    )
    hypotheses.llm_directions_path(problem_dir).write_text(
        "# llm\n\n## L4: restart by primal gap\n## L7 (=U2+L3): combined restarts\n"
    )
    for idea, status, score in [("L4", "discarded", "0.9"), ("L4", "discarded", "0.8"),
                                ("L4", "discarded", "0.7"), ("U2", "kept", "1.1")]:
        h = hypotheses.append(problem_dir, {"hypothesis": f"hyp under {idea}",
                                            "idea_refs": idea, "type": "user"})
        hypotheses.set_status(problem_dir, h["id"], status, score=score)
    tsv.append(problem_dir, {
        "candidate_file": "candidate_x.py", "score": "1.1", "delta": "0.2",
        "coverage": "1.0", "subset": "full", "status": "kept",
        "hypothesis": "local search on greedy", "hypothesis_id": "H4",
        "learnings": "2-opt converges in 1s",
    })
    knowledge = problem_dir / "research" / "knowledge"
    knowledge.mkdir(parents=True, exist_ok=True)
    (knowledge / "class-behavior.md").write_text(
        "# Class behavior\n\n- tight instances punish greedy fill order\n- large is LP-weak\n"
    )
    other = knowledge / "lp-bounds.md"
    other.write_text("# LP bounds\n\n- strongly correlated: gap > 1%\n")
    old = knowledge / "class-behavior.md"
    os.utime(old, (0, 0))  # order: lp-bounds newest, class-behavior older


def test_digest_contains_all_sections(tmp_path):
    pd = tmp_path / "mdkp"
    pd.mkdir()
    _seed(pd)
    text = digest.build(pd, 15, {"idea_pivot_n": 3})
    assert "U1: LP-guided priorities" in text          # user idea heads
    assert "L7: (=U2+L3) combined restarts" in text    # combined idea head keeps lineage
    assert "H4 [U2|user] kept 1.1" in text             # hypothesis tail
    assert "Current idea: U2" in text                  # latest terminal hypothesis
    assert "candidate_x.py" in text                    # kept candidates
    assert "small_0 100.00" in text                    # reference objectives
    assert "LP bounds" in text                         # knowledge tail (newest)
    assert text.count("\n") <= 80                       # bounded


def test_digest_pivot_required_variant(tmp_path):
    pd = tmp_path / "mdkp"
    pd.mkdir()
    _seed(pd)
    for _ in range(3):  # three consecutive discards under U2
        h = hypotheses.append(pd, {"hypothesis": "more", "idea_refs": "U2", "type": "user"})
        hypotheses.set_status(pd, h["id"], "discarded")
    text = digest.build(pd, 15, {"idea_pivot_n": 3})
    assert "PIVOT REQUIRED: idea U2" in text


def test_digest_new_idea_nudge(tmp_path):
    pd = tmp_path / "mdkp"
    pd.mkdir()
    _seed(pd)
    text = digest.build(pd, 15, {"new_idea_every_n": 1})  # 1 full row -> nudge fires
    assert "consider proposing a NEW idea" in text


def test_digest_empty_state_points_at_baselines(tmp_path):
    pd = tmp_path / "mdkp"
    pd.mkdir()
    text = digest.build(pd, 15, {"idea_pivot_n": 3})
    assert "No terminal hypotheses yet" in text
    assert "No kept candidates yet" in text
    assert "solvers/" in text  # working example pointer
    assert "(none yet - ask the owner to add ideas)" in text
