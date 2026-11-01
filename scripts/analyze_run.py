"""Bounded per-class summary of one eval run - the Analyst's primary input.

    uv run python scripts/analyze_run.py --problem mdkp --run 20260101T000000Z

Reads runs/<ts>/results.json plus problems/<p>/reference.json and prints a
~20-line summary (per instance-class mean ratio-to-reference, coverage, budget
utilization, worst instances, status counts) so the Analyst never reads the
raw results file wholesale.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import reference  # noqa: E402


def _cls(instance_name: str) -> str:
    return instance_name.rsplit("_", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", default="mdkp")
    parser.add_argument("--run", required=True, help="run id (runs/<run> directory name)")
    args = parser.parse_args()

    problem_dir = REPO_ROOT / "problems" / args.problem
    run_dir = REPO_ROOT / "runs" / args.run
    data = json.loads((run_dir / "results.json").read_text())
    rows = data["rows"]
    sense = data.get("sense", "min")
    refs = reference.objectives(problem_dir) or {}

    by_class: dict[str, list[dict]] = {}
    for r in rows:
        by_class.setdefault(_cls(r["instance"]), []).append(r)

    print(f"run {run_dir.name}: solver {data.get('solver', '?')} on {len(rows)} (instance, budget) pairs")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("statuses: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    print("per class (mean ratio-to-reference / coverage / mean wall_s):")
    for cls in sorted(by_class):
        crows = by_class[cls]
        ratios = []
        for r in crows:
            if r["status"] == "ok" and r["instance"] in refs and refs[r["instance"]] > 0:
                ratios.append(r["objective"] / refs[r["instance"]] if sense == "max"
                              else refs[r["instance"]] / r["objective"])
        cov = sum(1 for r in crows if r["status"] == "ok") / len(crows)
        wall = sum(r.get("wall_s") or 0.0 for r in crows) / len(crows)
        mean_ratio = sum(ratios) / len(ratios) if ratios else 0.0
        print(f"  {cls:8} ratio {mean_ratio:.4f}  cov {cov:.2f}  wall {wall:.2f}s")

    scored = [
        (r["objective"] / refs[r["instance"]] if sense == "max" else refs[r["instance"]] / r["objective"],
         r)  # noqa: E128
        for r in rows
        if r["status"] == "ok" and r["instance"] in refs and refs[r["instance"]] > 0
    ]
    if scored:
        scored.sort(key=lambda t: t[0])
        print("worst (instance, budget) pairs:")
        for ratio, r in scored[:5]:
            print(f"  {r['instance']:10} @{r['budget']:g}s  ratio {ratio:.4f}"
                  + (f"  log: {Path(r['log']).name}" if r.get("log") else ""))

    budgets = sorted({r["budget"] for r in rows})
    for b in budgets:
        brows = [r for r in rows if r["budget"] == b]
        wall = sum(r.get("wall_s") or 0.0 for r in brows) / len(brows)
        print(f"budget {b:g}s: mean wall {wall:.2f}s over {len(brows)} runs")
    print("solver logs: " + str(run_dir / "logs"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
