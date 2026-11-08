---
name: or-iterate
description: Runs one (or n) full iterations of the or_autoresearch loop interactively - digest orientation, Researcher/Implementor/Profiler/Analyst agents, full eval, bookkeeping. Use as /or-iterate [n].
---

# or-iterate: run the research loop in this session

You are the Orchestrator of the autoresearch loop. Follow `AGENTS.md` (the
protocol). Perform exactly ONE full iteration per invocation of this skill
(repeat n times only if the user passed a count argument). The optional
argument is a number of iterations; anything else is ignored.

Caveat: interactive mode commits bookkeeping to the CURRENT repo and branch -
run this on a dedicated branch unless you want the commits on your current
one. (The autonomous driver also runs in-place by default, committing to a
`loop/<problem>__<ts>` branch; only its `--isolate` flag uses a separate
`loop_runs/` workspace.) For Langfuse trace observability this session must
have been launched with telemetry env set - see `scripts/with_langfuse.sh`
(README "Observability").

Steps:

1. **Orient**: run `uv run python scripts/show_digest.py --problem mdkp` and
   treat its output as the authoritative state digest - do NOT re-read
   history.tsv, hypotheses.tsv, reference.json, or the idea files. If the
   digest shows the target reached, write `problems/mdkp/research/report.md`
   per AGENTS.md Phase 3 instead of iterating.
2. **Phase 2** exactly per AGENTS.md: spawn the named agents
   (`.claude/agents/`): researcher (with the digest text) -> implementor
   (battery until green, then smoke) -> profiler -> full eval via
   `uv run python evaluation/eval_solver.py --problem mdkp --solver <file>
   --subset full --hypothesis-id H<k> --hypothesis "..." --learnings "..."`
   -> analyst + researcher spawned together in ONE message (concurrently).
3. **Bookkeeping** (there is no driver here - you do it via the CLI, never
   with git directly): `uv run python scripts/finish_iteration.py --problem mdkp`.
4. Report a <=5-line summary (hypothesis, verdict kept/discarded, score,
   reference updates) and STOP. The user re-invokes `/or-iterate` to continue.

Hard rules (from AGENTS.md/CLAUDE.md, enforced here): never hand-edit
`benchmark/`, `reference.json`, the TSVs, or `ResearchDirectionsUser.md`;
battery + smoke before every full eval; no git commands (bookkeeping CLI
only); keep context lean - delegate to the agents, trust the digest.
