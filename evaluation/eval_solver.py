"""Common per-candidate evaluation CLI (problem-agnostic).

    uv run python evaluation/eval_solver.py --problem mdkp \
        --solver problems/mdkp/candidates/example_random.py \
        --subset smoke --hypothesis "baseline sanity run"

Runs the solver across every (instance, budget) pair of the subset in fresh
subprocesses (solver logs archived under runs/<ts>/logs/), scores against
reference.json with the configured scorer (default "auc"), updates
reference.json with any better solutions found, appends a history.tsv row
(with the subset used; a full row also resolves its hypothesis in
hypotheses.tsv), and writes runs/<ts>/.
"""

import argparse
import importlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import harness, hypotheses, reference, scoring, tsv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", default="mdkp", help="problem package under problems/")
    parser.add_argument("--solver", required=True, help="path to a solver .py file")
    parser.add_argument("--subset", default="full", choices=["smoke", "full"])
    parser.add_argument("--budgets", default=None, help="comma-separated seconds, overrides config")
    parser.add_argument("--label", default=None, help="defaults to solver filename")
    parser.add_argument("--no-preflight", action="store_true",
                        help="skip the automatic preflight crash-check (default: run it "
                             "first; on failure exit 2 without writing anything)")
    parser.add_argument("--hypothesis", default="")
    parser.add_argument("--hypothesis-id", default="",
                        help="id from hypotheses.tsv; a full row resolves it (kept/discarded)")
    parser.add_argument("--learnings", default="")
    parser.add_argument("--scorer", default=None,
                        help="scorer registry key; default benchmark_config.SCORER / 'auc'")
    args = parser.parse_args()
    PROBLEM = args.problem

    cfg = importlib.import_module(f"problems.{PROBLEM}.benchmark_config")
    sense = getattr(cfg, "SENSE", scoring.SENSE_MIN)
    scorer_name = args.scorer or getattr(cfg, "SCORER", "auc")
    if importlib.util.find_spec(f"problems.{PROBLEM}.scorers"):
        importlib.import_module(f"problems.{PROBLEM}.scorers")  # problem-local plugins

    problem_dir = REPO_ROOT / "problems" / PROBLEM
    solver_path = Path(args.solver).resolve()
    label = args.label or solver_path.name
    budgets = (
        [float(b) for b in args.budgets.split(",")]
        if args.budgets
        else [float(b) for b in cfg.TIME_BUDGETS]
    )

    ref_objs = reference.objectives(problem_dir)
    if ref_objs is None:
        print(f"error: {reference.path_for(problem_dir)} missing - run scripts/run_reference.py first")
        return 2

    if not args.no_preflight:
        from autoresearch import preflight
        res = preflight.run_preflight(PROBLEM, solver_path, REPO_ROOT)
        print(preflight.report(res))
        if res["status"] != "ok":
            return 2  # nothing written: no TSV row, no runs/ dir, no reference update

    instances = harness.load_instances(PROBLEM, args.subset, REPO_ROOT)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = REPO_ROOT / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = harness.evaluate(PROBLEM, solver_path, instances, budgets, REPO_ROOT,
                            log_dir=out_dir / "logs")
    (out_dir / "results.json").write_text(
        json.dumps(
            {
                "problem": PROBLEM,
                "solver": label,
                "subset": args.subset,
                "budgets": budgets,
                "hypothesis_id": args.hypothesis_id,
                "scorer": scorer_name,
                "sense": sense,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )

    score = scoring.run(scorer_name, rows, ref_objs, sense)
    found = scoring.best_objectives(rows, sense)
    changed = reference.update(problem_dir, found, source=label, sense=sense)

    prev_best = tsv.best_score(tsv.read(problem_dir))
    # kept = this run advanced best-known (reference.json) or is the first scored
    # run. The ratio score is not comparable across reference eras: once
    # references improve, later solvers score ~1.0 against their own
    # contributions and can never exceed a historical score measured against
    # weaker references.
    status = tsv.KEPT if prev_best is None or changed else tsv.DISCARDED
    delta = score["score"] - prev_best if prev_best is not None else None

    row_written = tsv.append(
        problem_dir,
        {
            "candidate_file": label,
            "score": f"{score['score']:.6f}",
            "delta": "" if delta is None else f"{delta:.6f}",
            "coverage": f"{score['coverage']:.4f}",
            "subset": args.subset,
            "status": status,
            "hypothesis": args.hypothesis,
            "hypothesis_id": args.hypothesis_id,
            "learnings": args.learnings,
        },
    )
    resolved = hypotheses.resolve_from_history(problem_dir, row_written)
    (out_dir / "score.json").write_text(
        json.dumps({k: score.get(k) for k in ("scorer", "score", "auc", "per_budget", "coverage")}
                   | {"status": status}, indent=2) + "\n"
    )

    print(f"solver={label} subset={args.subset} budgets={budgets} scorer={scorer_name} sense={sense}")
    for b, mean in score.get("per_budget", {}).items():
        print(f"  budget {b:>5.1f}s: mean score {mean:.4f}")
    print(
        f"score: {score['score']:.4f} | coverage: {score['coverage']:.2f} | "
        f"status: {status} | best-so-far: {max(score['score'], prev_best) if prev_best is not None else score['score']:.4f}"
    )
    if resolved:
        print(f"hypothesis {resolved} -> {status}")
    if changed:
        ref_now = reference.objectives(problem_dir)
        for name in changed:
            print(f"  reference updated: {name} {ref_objs[name]:.2f} -> {ref_now[name]:.2f}")
    print(f"results: {out_dir.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
