"""Render the experiment log: history.tsv joined with hypotheses.tsv.

    uv run python scripts/experiment_log.py                 # all evals
    uv run python scripts/experiment_log.py --full          # counted iterations only
    uv run python scripts/experiment_log.py --problem mdkp

One line per evaluation: iteration, subset, hypothesis id (joined to its idea
and type), candidate, score, delta, coverage, verdict, learnings. Footer:
kept candidates and the best full-subset score.
"""

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import hypotheses as hyp, tsv  # noqa: E402


def _one(text: str, limit: int) -> str:
    single = " ".join(str(text or "").split())
    return single if len(single) <= limit else single[: limit - 3] + "..."


def load_experiment_log(problem_dir: Path, full_only: bool = False) -> list[dict]:
    """History rows enriched with their hypothesis (idea ref, type)."""
    hyps = {r["id"]: r for r in hyp.read(problem_dir)}
    rows = tsv.read(problem_dir)
    if full_only:
        rows = tsv.full_rows(rows)
    out = []
    for r in rows:
        h = hyps.get((r.get("hypothesis_id") or "").strip(), {})
        out.append({**r, "idea_refs": h.get("idea_refs", ""), "htype": h.get("type", "")})
    return out


def render(rows: list[dict]) -> str:
    lines = [
        f"{'it':>2} {'sub':5} {'H':>3} {'idea':4} {'typ':4} {'candidate':34} "
        f"{'score':>9} {'delta':>9} {'cov':>6}  {'status':9} learnings"
    ]
    for r in rows:
        lines.append(
            f"{r.get('iteration', '?'):>2} {r.get('subset', '?'):5} "
            f"{r.get('hypothesis_id') or '-':>3} {r.get('idea_refs') or '-':4} "
            f"{r.get('htype') or '-':4} {(r.get('candidate_file') or '-')[:34]:34} "
            f"{r.get('score') or '-':>9} {r.get('delta') or '-':>9} "
            f"{r.get('coverage') or '-':>6}  {r.get('status') or '-':9} "
            f"{_one(r.get('learnings'), 44)}"
        )
    full = [r for r in rows if r.get("subset") == tsv.FULL]
    scored = [r for r in full if r.get("score")]
    if scored:
        best = max(scored, key=lambda r: float(r["score"]))
        lines.append(f"best full-eval: {best['candidate_file']} score {best['score']}")
    kept = [r for r in rows if r.get("status") == tsv.KEPT]
    if kept:
        lines.append("kept: " + ", ".join(sorted({r["candidate_file"] for r in kept})))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", default="mdkp")
    parser.add_argument("--full", action="store_true", help="full-subset iterations only")
    args = parser.parse_args()

    problem_dir = REPO_ROOT / "problems" / args.problem
    rows = load_experiment_log(problem_dir, full_only=args.full)
    if not rows:
        print("(no evaluations yet)")
        return 0
    print(render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
