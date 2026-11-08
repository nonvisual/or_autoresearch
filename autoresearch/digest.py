"""Compact per-iteration state digest for prompt injection (driver or skill).

The digest is embedded in each iteration prompt (or printed by
scripts/show_digest.py for the interactive mode) so the session never re-reads
history.tsv, hypotheses.tsv, reference.json, or the ResearchDirections files
during orientation. Bounded to ~80 lines. Problem-agnostic: everything goes
through autoresearch.tsv / reference / hypotheses and the research/ convention
inside the problem package.
"""

from pathlib import Path

from autoresearch import hypotheses, reference, tsv
from autoresearch.textutil import one_line

TAIL_ROWS = 5
LLM_HEADS = 8
HYP_TAIL = 4
HEAD_LIMIT = 80
KNOWLEDGE_FILES = 2
KNOWLEDGE_LINES = 5


def kept_recent(rows: list[dict], k: int = 3) -> list[dict]:
    """Most recent kept full-subset rows, newest first, deduplicated by file.

    Recency, not score: ratio scores are not comparable across reference eras
    (see eval_solver), and the newest kept candidate is the natural working
    example for the next implementation.
    """
    seen: set[str] = set()
    picked: list[dict] = []
    for r in reversed(tsv.full_rows(rows)):
        label = r.get("candidate_file", "")
        if r.get("status") != tsv.KEPT or label in seen:
            continue
        seen.add(label)
        picked.append(r)
        if len(picked) == k:
            break
    return picked


def _trunc(value: str, limit: int = 60) -> str:
    return one_line(value, limit)


def build(problem_dir: Path, target: int, hyper: dict | None = None,
          pivot: dict | None = None) -> str:
    """Render the digest text for the current state of one problem package.

    ``pivot``: an already-computed ``hypotheses.pivot_state`` result (the driver
    has one; passing it saves a re-read and guarantees the same state).
    """
    hyper = hyper or {}
    pivot_n = int(hyper.get("idea_pivot_n", 3))
    new_idea_every = hyper.get("new_idea_every_n")
    max_per_idea = hyper.get("max_hypotheses_per_idea")
    rows = tsv.read(problem_dir)
    hyp_rows = hypotheses.read(problem_dir)
    terminal = [r for r in hyp_rows if r.get("status") in hypotheses.TERMINAL]
    full = tsv.full_rows(rows)
    problem = problem_dir.name
    lines: list[str] = [
        "=== STATE DIGEST (generated; trust this, do not re-read history.tsv /",
        "hypotheses.tsv / reference.json / ResearchDirections*.md / knowledge/)",
        "===",
        f"Full-subset iterations: {len(full)}/{target} complete.",
    ]

    st = pivot if pivot is not None else hypotheses.pivot_state(problem_dir, pivot_n)
    if st["current_idea"] is None:
        lines.append("No terminal hypotheses yet - pick any idea (prefer an untried user idea U*).")
    elif st["must_pivot"]:
        lines.append(
            f"PIVOT REQUIRED: idea {st['current_idea']} has {st['consecutive_discards']} "
            f"consecutive discards - the Researcher must select a DIFFERENT idea this iteration."
        )
    else:
        lines.append(
            f"Current idea: {st['current_idea']} - {st['consecutive_discards']} discard(s) in a "
            f"row (pivot after {pivot_n})."
        )
    if max_per_idea is not None:
        tried = sum(1 for r in terminal if r.get("idea_refs") == st["current_idea"])
        lines.append(
            f"Hypotheses under the current idea: {tried}/{int(max_per_idea)} "
            "(max_hypotheses_per_idea - once at the cap, prefer a different idea)."
        )
    if new_idea_every and full and len(full) % int(new_idea_every) == 0:
        lines.append(f"Nudge: every {int(new_idea_every)} iterations, consider proposing a NEW idea.")

    user_heads = hypotheses.parse_idea_heads(hypotheses.user_directions_path(problem_dir))
    llm_heads = hypotheses.parse_idea_heads(hypotheses.llm_directions_path(problem_dir))
    lines.append("")
    lines.append("User ideas (ResearchDirectionsUser.md - read-only for agents):")
    if user_heads:
        lines.extend(f"  {iid}: {_trunc(text, HEAD_LIMIT)}" for iid, text in user_heads)
    else:
        lines.append("  (none yet - ask the owner to add ideas)")
    lines.append(f"LLM ideas (ResearchDirectionsLLM.md, last {LLM_HEADS}):")
    if llm_heads:
        lines.extend(
            f"  {iid}: {_trunc(text, HEAD_LIMIT)}" for iid, text in llm_heads[-LLM_HEADS:]
        )
    else:
        lines.append("  (none yet)")

    if terminal:
        lines.append("")
        lines.append("Recent hypotheses (newest first):")
        for r in reversed(terminal[-HYP_TAIL:]):
            lines.append(
                f"  {r.get('id', '?')} [{r.get('idea_refs') or '-'}|{r.get('type') or '-'}] "
                f"{r.get('status', '?')} {r.get('score') or '-'} - {_trunc(r.get('hypothesis'))}"
            )

    recent = kept_recent(rows)
    if recent:
        lines.append(f"Latest kept candidate: {recent[0]['candidate_file']} (score {recent[0]['score']}).")
    else:
        lines.append("No kept candidates yet - the first full evals set the bar.")

    open_hyps = [r for r in hyp_rows
                 if r.get("status") in (hypotheses.PROPOSED, hypotheses.RUNNING)]
    if open_hyps:
        lines.append("")
        lines.append("OPEN hypotheses (not yet fully evaluated - RESUME these, do not re-record):")
        for r in open_hyps[-3:]:
            lines.append(
                f"  {r.get('id', '?')} [{r.get('idea_refs') or '-'}] {r.get('status', '?')} "
                f"{r.get('candidate_file') or '-'} - {_trunc(r.get('hypothesis'))}"
            )

    if rows:
        lines.append("")
        lines.append("Recent history.tsv rows (oldest first; score, cov = coverage, hid = hypothesis):")
        for r in rows[-TAIL_ROWS:]:
            lines.append(
                f"  #{r.get('iteration', '?')}  {r.get('subset', '?'):5}  {r.get('status', '?'):9}  "
                f"{r.get('candidate_file', '?')}  score {r.get('score') or '-'}  "
                f"cov {r.get('coverage') or '-'}  hid {r.get('hypothesis_id') or '-'}  "
                f"hyp: {_trunc(r.get('hypothesis'))} | learn: {_trunc(r.get('learnings'))}"
            )

    lines.append("")
    if recent:
        lines.append(
            "Kept candidates (most recent first; give the FIRST to the "
            "implementer as its working example):"
        )
        lines.append("  " + " | ".join(f"{r['candidate_file']}" for r in recent))
    else:
        lines.append(
            f"Working example for the implementer: the strongest baseline in "
            f"problems/{problem}/solvers/ (or candidates/example_random.py for the bare contract)."
        )

    refs = reference.objectives(problem_dir)
    if refs:
        lines.append("")
        lines.append(
            "reference.json best-known objectives: "
            + " ".join(f"{name} {obj:.2f}" for name, obj in refs.items())
        )

    knowledge_dir = problem_dir / "research" / "knowledge"
    files = sorted(knowledge_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)[-KNOWLEDGE_FILES:]
    if files:
        lines.append("")
        lines.append("knowledge/ (most recent topics, tails):")
        for f in reversed(files):
            content = [ln for ln in f.read_text().splitlines() if ln.strip()]
            heading = next((ln.lstrip("# ").strip() for ln in content if ln.startswith("# ")), f.stem)
            tail = " / ".join(_trunc(ln.lstrip("- ")) for ln in content[-KNOWLEDGE_LINES:])
            lines.append(f"  {f.stem} [{heading}]: {tail}")

    lines.append("=== END DIGEST ===")
    return "\n".join(lines)
