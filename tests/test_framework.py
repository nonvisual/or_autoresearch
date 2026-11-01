"""Framework units: scoring (senses + registry), tsv, reference, harness."""

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pytest

from autoresearch import harness, reference, scoring, tsv
from problems.mdkp.generator import make_instance


def _rows():
    return [
        {"instance": "a", "budget": 1.0, "status": "ok", "objective": 100.0},
        {"instance": "a", "budget": 5.0, "status": "ok", "objective": 110.0},
        {"instance": "b", "budget": 1.0, "status": "timeout", "objective": None},
        {"instance": "b", "budget": 5.0, "status": "ok", "objective": 55.0},
    ]


def test_instance_score_min_ratio():
    assert scoring.instance_score(90.0, 100.0) == pytest.approx(0.9)
    with pytest.raises(ValueError):
        scoring.instance_score(90.0, 0.0)  # non-positive objective


def test_instance_score_max_ratio():
    assert scoring.instance_score(200.0, 220.0, "max") == pytest.approx(1.1)  # beat reference
    with pytest.raises(ValueError):
        scoring.instance_score(0.0, 10.0, "max")  # non-positive reference


def test_score_rows_min_sense():
    s = scoring.score_rows(_rows(), {"a": 100.0, "b": 50.0})
    assert s["per_budget"][1.0] == pytest.approx(0.5)  # a scores 1.0, b timeout scores 0.0
    assert s["per_budget"][5.0] == pytest.approx((100.0 / 110.0 + 50.0 / 55.0) / 2)
    assert s["coverage"] == pytest.approx(0.75)
    assert s["auc"] == pytest.approx((0.5 + (100.0 / 110.0 + 50.0 / 55.0) / 2) / 2)


def test_score_rows_max_sense():
    s = scoring.score_rows(_rows(), {"a": 100.0, "b": 50.0}, "max")
    assert s["per_budget"][1.0] == pytest.approx(0.5)  # a scores 1.0, b timeout scores 0.0
    assert s["per_budget"][5.0] == pytest.approx((110.0 / 100.0 + 55.0 / 50.0) / 2)


def test_best_objectives_respects_sense():
    assert scoring.best_objectives(_rows(), "min")["a"] == pytest.approx(100.0)
    assert scoring.best_objectives(_rows(), "max")["a"] == pytest.approx(110.0)


def test_is_better_flips_with_sense():
    assert scoring.is_better(1.0, 2.0, "min")
    assert scoring.is_better(2.0, 1.0, "max")
    assert not scoring.is_better(1.0, 1.0, "max")  # strict only


def test_registry_default_auc():
    out = scoring.run("auc", _rows(), {"a": 100.0, "b": 50.0}, "max")
    assert out["scorer"] == "auc"
    assert out["score"] == pytest.approx(out["auc"])


def test_registry_unknown_scorer_raises():
    with pytest.raises(ValueError):
        scoring.get("nope")


def test_registry_requires_score_key():
    @scoring.register("tmp_bad")
    def _bad(rows, reference, sense):
        return {"no_score": 1}

    with pytest.raises(ValueError):
        scoring.run("tmp_bad", _rows(), {"a": 1.0, "b": 1.0}, "max")


def test_registry_custom_scorer():
    @scoring.register("tmp_cov")
    def _cov(rows, reference, sense):
        return {"score": scoring.coverage(rows)}

    assert scoring.run("tmp_cov", _rows(), {}, "max")["score"] == pytest.approx(0.75)


def test_tsv_roundtrip_with_hypothesis_id(tmp_path):
    row = tsv.append(tmp_path, {
        "candidate_file": "candidate_x.py", "score": "1.0", "delta": "0.1",
        "coverage": "1.0", "subset": "full", "status": "kept",
        "hypothesis": "dual price\tgreedy", "hypothesis_id": "H1",
        "learnings": "line1\nline2",
    })
    assert row["iteration"] == 1
    rows = tsv.read(tmp_path)
    assert len(rows) == 1
    assert rows[0]["hypothesis_id"] == "H1"
    assert "\t" not in rows[0]["hypothesis"]  # sanitized
    assert "\n" not in rows[0]["learnings"]
    assert tsv.count_full(tmp_path) == 1
    assert tsv.best_score(rows) == pytest.approx(1.0)


def test_tsv_plateau():
    rows = [{"score": "1.0", "subset": "full"}] * 3 + [{"score": "1.0", "subset": "full"}] * 4
    assert tsv.plateau(rows, window=4)  # no improvement in the last 4
    rows2 = [{"score": "1.0", "subset": "full"}] * 3 + [{"score": "1.2", "subset": "full"}] * 4
    assert not tsv.plateau(rows2, window=4)


def test_reference_update_max_strict_improvements(tmp_path):
    reference.build(tmp_path, {"a": 100.0, "b": 50.0}, problem="mdkp")
    changed = reference.update(tmp_path, {"a": 110.0, "b": 40.0}, source="cand.py", sense="max")
    assert changed == ["a"]  # only the strict improvement
    objs = reference.objectives(tmp_path)
    assert objs["a"] == pytest.approx(110.0)
    assert objs["b"] == pytest.approx(50.0)
    assert reference.update(tmp_path, {"a": 110.0}, source="other.py", sense="max") == []


def _write_instance(tmp_path, name="tiny"):
    inst = make_instance(12, 2, "none", 0.4, 3)
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(inst.to_dict()))
    return path


def _write_solver(tmp_path, body, name="solver.py"):
    path = tmp_path / name
    path.write_text(body)
    return path


OK_SOLVER = (
    "from problems.mdkp.problem import MDKPSolution\n"
    "def solve(instance, time_budget_s):\n"
    "    return MDKPSolution([0])\n"
)

INFEASIBLE_SOLVER = (
    "from problems.mdkp.problem import MDKPSolution\n"
    "def solve(instance, time_budget_s):\n"
    "    return MDKPSolution(list(range(instance.n)))\n"  # all items: over capacity
)

CRASH_SOLVER = (
    "def solve(instance, time_budget_s):\n"
    "    raise RuntimeError('boom')\n"
)

SLEEP_SOLVER = (
    "import time\n"
    "from problems.mdkp.problem import MDKPSolution\n"
    "def solve(instance, time_budget_s):\n"
    "    time.sleep(5.0)\n"
    "    return MDKPSolution([0])\n"
)

NOISY_SOLVER = (
    "import sys\n"
    "from problems.mdkp.problem import MDKPSolution\n"
    "def solve(instance, time_budget_s):\n"
    "    print('progress line that is not the payload')\n"
    "    sys.stderr.write('diagnostic: chose item 0\\n')\n"
    "    return MDKPSolution([0])\n"
)


def test_harness_ok_row(tmp_path):
    res = harness.run_single("mdkp", _write_solver(tmp_path, OK_SOLVER),
                             _write_instance(tmp_path), 1.0, REPO_ROOT)
    assert res["status"] == "ok"
    assert res["objective"] > 0.0
    assert res["wall_s"] > 0.0


def test_harness_kills_overruns(tmp_path):
    t0 = time.perf_counter()
    res = harness.run_single("mdkp", _write_solver(tmp_path, SLEEP_SOLVER),
                             _write_instance(tmp_path), 0.5, REPO_ROOT)
    wall = time.perf_counter() - t0
    assert res["status"] == "timeout"
    assert wall < 3.0  # killed at budget * 1.25, not after the full sleep


def test_harness_infeasible_and_error(tmp_path):
    res = harness.run_single("mdkp", _write_solver(tmp_path, INFEASIBLE_SOLVER),
                             _write_instance(tmp_path), 1.0, REPO_ROOT)
    assert res["status"] == "infeasible"
    res = harness.run_single("mdkp", _write_solver(tmp_path, CRASH_SOLVER),
                             _write_instance(tmp_path), 1.0, REPO_ROOT)
    assert res["status"] == "error"
    assert "boom" in res["detail"]


def test_harness_log_capture(tmp_path):
    log_dir = tmp_path / "logs"
    res = harness.run_single("mdkp", _write_solver(tmp_path, NOISY_SOLVER),
                             _write_instance(tmp_path, "smoke_like"), 1.0, REPO_ROOT,
                             log_dir=log_dir)
    assert res["status"] == "ok"
    assert res["log_tail"].endswith("chose item 0\n") or "chose item 0" in res["log_tail"]
    log = Path(res["log"])
    assert log.exists()
    content = log.read_text()
    assert "diagnostic: chose item 0" in content
    assert "progress line that is not the payload" in content  # stdout beyond payload archived


def test_harness_log_fields_empty_when_quiet(tmp_path):
    res = harness.run_single("mdkp", _write_solver(tmp_path, OK_SOLVER),
                             _write_instance(tmp_path), 1.0, REPO_ROOT)
    assert res["log"] == ""
    assert res["log_tail"] == ""
