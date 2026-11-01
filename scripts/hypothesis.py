"""CLI over autoresearch/hypotheses.py - the Researcher agent's only write path.

    uv run python scripts/hypothesis.py add  --problem mdkp \
        --hypothesis "dual-price greedy with restarts" --idea-ref U1 --type user \
        --notes "first try: LP duals order items better than static ratios"
    uv run python scripts/hypothesis.py start --problem mdkp --id H3 \
        --candidate candidate_dual.py
    uv run python scripts/hypothesis.py list --problem mdkp [--status running]

Type follows the driving idea's owner (user ideas -> "user", LLM ideas ->
"llm"). ``add`` prints the assigned hypothesis id; the orchestrator passes it
to the full eval via ``--hypothesis-id``.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import hypotheses  # noqa: E402


def main() -> int:
    # --problem lives on each subparser so it can follow the subcommand
    # (``hypothesis.py add --problem mdkp ...``), which is how the agents call it.
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="record a new hypothesis (status proposed)")
    p_add.add_argument("--problem", default="mdkp")
    p_add.add_argument("--hypothesis", required=True)
    p_add.add_argument("--idea-ref", required=True,
                       help="single primary idea id, e.g. U2 or L7 (combinations are new L ids)")
    p_add.add_argument("--type", required=True, choices=["user", "llm"])
    p_add.add_argument("--notes", default="", help="one-line rationale (persisted)")

    p_start = sub.add_parser("start", help="mark a hypothesis running with its candidate file")
    p_start.add_argument("--problem", default="mdkp")
    p_start.add_argument("--id", required=True)
    p_start.add_argument("--candidate", required=True, help="candidate filename")

    p_list = sub.add_parser("list", help="print hypotheses (one line each)")
    p_list.add_argument("--problem", default="mdkp")
    p_list.add_argument("--status", default=None)

    args = parser.parse_args()
    problem_dir = REPO_ROOT / "problems" / args.problem

    if args.cmd == "add":
        row = hypotheses.append(
            problem_dir,
            {
                "hypothesis": args.hypothesis,
                "idea_refs": args.idea_ref,
                "type": args.type,
                "notes": args.notes,
            },
        )
        print(f"added {row['id']} [{row['idea_refs']}|{row['type']}] (status {row['status']})")
        return 0

    if args.cmd == "start":
        row = hypotheses.mark_running(problem_dir, args.id, args.candidate)
        print(f"{row['id']} running as {row['candidate_file']}")
        return 0

    rows = hypotheses.read(problem_dir)
    if args.status:
        rows = [r for r in rows if r.get("status") == args.status]
    if not rows:
        print("(no hypotheses)")
        return 0
    for r in rows:
        print(
            f"{r.get('id', '?')}  [{r.get('idea_refs') or '-'}|{r.get('type') or '-'}]  "
            f"{r.get('status', '?'):9}  {r.get('candidate_file') or '-':32}  "
            f"{r.get('score') or '-':>9}  {_one(r.get('hypothesis'))}"
        )
    return 0


def _one(text: str, limit: int = 70) -> str:
    single = " ".join(str(text or "").split())
    return single if len(single) <= limit else single[: limit - 3] + "..."


if __name__ == "__main__":
    sys.exit(main())
