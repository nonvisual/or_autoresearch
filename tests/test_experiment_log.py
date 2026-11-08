"""Experiment log viewer: join and render."""

from pathlib import Path

from autoresearch import hypotheses as hyp, tsv
from scripts.experiment_log import load_experiment_log, render


def _seed(tmp_path):
    pd = tmp_path / "mdkp"
    (pd / "research").mkdir(parents=True)
    hyp.append(pd, {"hypothesis": "beam search", "idea_refs": "U1", "type": "user"})
    hyp.mark_running(pd, "H1", "candidate_beam.py")
    tsv.append(pd, {
        "candidate_file": "candidate_beam.py", "score": "0.997137", "delta": "-0.001",
        "coverage": "1.0000", "subset": "full", "status": "discarded",
        "hypothesis": "beam search", "hypothesis_id": "H1", "learnings": "width saturates",
    })
    tsv.append(pd, {
        "candidate_file": "candidate_beam.py", "score": "0.998289", "delta": "0.2",
        "coverage": "1.0000", "subset": "smoke", "status": "kept",
        "hypothesis": "beam search", "hypothesis_id": "H1", "learnings": "",
    })
    return pd


def test_load_joins_hypothesis_fields(tmp_path):
    pd = _seed(tmp_path)
    rows = load_experiment_log(pd)
    full_row = next(r for r in rows if r["subset"] == "full")
    assert full_row["hypothesis_id"] == "H1"
    assert full_row["idea_refs"] == "U1"   # joined from hypotheses.tsv
    assert full_row["htype"] == "user"


def test_render_table_and_footer(tmp_path):
    pd = _seed(tmp_path)
    text = render(load_experiment_log(pd))
    assert "candidate_beam.py" in text and "0.997137" in text and "U1" in text
    assert "best full-eval: candidate_beam.py score 0.997137" in text
    assert "kept: candidate_beam.py" in text


def test_full_only_filter(tmp_path):
    pd = _seed(tmp_path)
    rows = load_experiment_log(pd, full_only=True)
    assert len(rows) == 1 and rows[0]["subset"] == "full"
