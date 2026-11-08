# Auto-Research Protocol (or_autoresearch)

You are running an autonomous research loop that improves solvers for one
optimization problem, iteratively and measurably. This file is the protocol.
Problem: `mdkp` (0-1 multidimensional knapsack, MAXIMIZATION of total profit
under m capacity dimensions) - the problem package under `problems/mdkp/`.

## Running modes (dual usage)

1. **Autonomous**: an external driver invokes you once per iteration
   (`scripts/run_loop.py`, headless). Each invocation performs AT MOST ONE full
   iteration, then stops. The driver does all bookkeeping after you stop. By
   default the driver runs IN-PLACE: the repo itself is your working tree and
   bookkeeping commits go to a `loop/<problem>__<ts>` branch (never main).
   With `--isolate` it runs in a full-copy throwaway workspace instead
   (parallel-safe).
2. **Interactive**: the `/or-iterate` skill in a Claude Code session. You are
   the Orchestrator; run `uv run python scripts/show_digest.py --problem mdkp`
   for orientation, perform ONE iteration per invocation, then run
   `uv run python scripts/finish_iteration.py --problem mdkp` for bookkeeping.

Same protocol either way. "The digest" below means the driver-injected digest
or the `show_digest.py` output, whichever mode you are in.

## Repo map

- `autoresearch/` - framework: harness, scoring, reference.json, history.tsv,
  hypotheses.tsv, solver battery. Do not modify it during research; extend it
  only with a `refactor:` commit if something is genuinely broken.
- `evaluation/eval_solver.py` - THE evaluation CLI. Never write a per-problem
  eval script.
- `scripts/` - hypothesis CLI (the Researcher's write path), test_solver battery,
  analyze_run (Analyst feed), experiment_log (rendered history x hypotheses
  view), show_digest, run_reference, run_loop (autonomous driver),
  finish_iteration.
- `problems/mdkp/` - the problem: schema, generator, evaluator, benchmark
  config, `solvers/` (reference baselines), `candidates/` (your solvers),
  `research/` (state: idea files, hypotheses.tsv, history.tsv, knowledge/).
- `problems/mdkp/benchmark/` - READ-ONLY instance files.
- `.claude/agents/` - the four named subagents: implementor, profiler,
  analyst, researcher.
- `loop.json` - loop configuration (problem, iterations, hyperparameters,
  driver caps); re-read every driver iteration. `.env` - LLM + observability
  keys for the driver (see `.env.example`).
- `runs/<UTC timestamp>/` - raw eval outputs: `results.json`, `score.json`,
  and `logs/` (gitignored).

## Solver contract

A candidate is ONE file: `problems/mdkp/candidates/candidate_<short_name>.py`
defining `solve(instance, time_budget_s) -> Solution` - the inputs are the
instance and the timeout, nothing else. ANY algorithm is welcome: MIP is NOT
required (greedy, local search, metaheuristics, matheuristics all fine; HiGHS
via highspy is available if you want it). Rules:

- It is loaded in a fresh subprocess per run. No shared state, no caching on disk.
- Import time counts against the budget. Prefer numpy over heavy frameworks.
- Must respect `time_budget_s` wall-clock: return the best solution found so
  far before it expires. The harness kills at `budget * 1.25` - a killed run
  scores 0.0.
- Must be deterministic given the instance and budget: fixed seeds only
  (`np.random.default_rng(<constant>)` - never entropy or the clock), and
  drive the algorithm by iteration counts, using the time budget only as a
  safety cap, so consecutive executions give the same result.
- Solvers may emit diagnostics on stderr; stdout is reserved for the harness
  payload. The Analyst reads the archived logs.

## Scoring

Per (instance, budget): `0.0` if no feasible solution, else
`objective / reference_best` (MAXIMIZATION; above 1.0 means the run beat the
current reference). Mean across instances per budget; AUC = mean across
budgets (objective quality at each timeout). `reference.json` holds the best
known objective per instance and is updated automatically by
`evaluation/eval_solver.py` whenever a run finds something better. The scorer
is pluggable (`--scorer`, registry in `autoresearch/scoring.py`; default `auc`).

## Research state (read via the digest; written via CLIs only)

- `research/ResearchDirectionsUser.md` - the owner's ideas (`U1, U2, ...`).
  READ-ONLY for every agent; synced host -> workspace fresh each iteration.
- `research/ResearchDirectionsLLM.md` - agent-contributed ideas (`L1, L2, ...`).
  Combining ideas appends a NEW heading referencing its sources
  (`## L7 (=U2+L3): ...`); hypotheses derived from it reference `L7`.
- `research/hypotheses.tsv` - every hypothesis chosen for experimentation
  (id, idea ref, type user|llm, candidate, status proposed->running->kept|discarded).
- `research/knowledge/` - the Analyst's wiki of problem learnings.

## Iteration economy

- One iteration = one full-subset evaluation row (`subset == "full"`) in
  `problems/mdkp/research/history.tsv`. Smoke-only runs are free and do not count.
- The digest states the full-row count. If the target is reached, do Phase 3
  and stop. Otherwise perform exactly ONE iteration (Phase 2) and stop. Never
  run two full evals in one invocation.
- Never delete a `kept` candidate file.

## Hard rules

1. Never write to `benchmark/`, `reference.json`, `history.tsv`,
   `hypotheses.tsv`, or `ResearchDirectionsUser.md` by hand. Instances are
   regenerated only via the generator; reference/TSVs only via the CLIs.
2. Every candidate goes through the battery first
   (`uv run python scripts/test_solver.py --problem mdkp --solver <file>`),
   then `--subset smoke`, then `--subset full`. Fix the code; do not retry blindly.
3. Every full evaluation goes through
   `uv run python evaluation/eval_solver.py --problem mdkp --solver <file>
   --subset full --hypothesis-id H<k> --hypothesis "<one line>" --learnings "<one line>"`
   - that is what writes the TSV row and resolves the hypothesis. The eval
   runs a preflight crash-check first; on `PREFLIGHT FAIL` it exits 2 and
   writes NOTHING - fix the candidate, do not retry.
4. Deterministic seeds everywhere. Nothing may depend on wall-clock or entropy.
5. uv only, never pip. No emojis. Do not run git - bookkeeping commits.
6. Keep context small: this file, the digest, and the latest eval summary are
   all you need per iteration.
7. If it isn't written to a file, it didn't happen: rationale via
   `hypothesis.py add --notes`, profiler timings folded into `--learnings`,
   analysis into `knowledge/` or `notes/`.

## Agent boundaries (context-overload control)

- **Orchestrator (you)**: consume the digest and one-line subagent reports;
  never read history/hypotheses/reference files or results.json wholesale;
  never implement yourself.
- **researcher**: gets the digest; may read the ONE idea body it selected;
  writes only via `scripts/hypothesis.py`.
- **implementor**: gets contract + `problem.py` API + working example +
  hypothesis + target path; no research state access.
- **profiler**: gets the candidate path; no research state access; must not
  change behavior.
- **analyst**: gets the eval summary + run id; reads `analyze_run.py` output,
  targeted log tails; writes `ResearchDirectionsLLM.md` and `knowledge/`.

## Phase 0 - Orientation (start of every invocation)

1. Read the digest. It is current and authoritative - do NOT re-read
   `history.tsv`, `hypotheses.tsv`, `reference.json`, or the idea files.
2. If the digest shows the target number of full rows complete, do Phase 3
   and stop.
3. First invocation only: if `problems/mdkp/reference.json` does not exist, run
   `uv run python scripts/run_reference.py --problem mdkp --subset full --budgets 1,5,20,60` once;
   if `benchmark/` is missing, run `uv run python -m problems.mdkp.generator`.

## Phase 2 - One iteration

1. **Researcher** (spawn the `researcher` agent with the digest text):
   it selects an idea honoring the digest's pivot constraint
   (`max_hypotheses_per_idea`, `new_idea_every_n` as nudges), picks or
   formulates ONE hypothesis, records it via
   `uv run python scripts/hypothesis.py add --problem mdkp --hypothesis "..."
   --idea-ref <single idea id> --type user|llm --notes "<rationale>"`
   and marks it running once a candidate filename is chosen
   (`scripts/hypothesis.py start --id H<k> --candidate candidate_<name>.py`).
   One change per hypothesis - no bundles.
2. **Implementor** (spawn the `implementor` agent). Give it ONLY: the solver
   contract above, `problems/mdkp/problem.py` + `evaluator.py` API, the
   digest's top kept candidate as a working example (first iteration:
   `problems/mdkp/solvers/baseline_greedy.py`), the exact hypothesis, and the
   target file path. It iterates until the battery
   (`scripts/test_solver.py`) is green, then runs the smoke eval.
   It does not need the history.
3. **Profiler** (spawn the `profiler` agent on the new candidate): measure
   import time, cProfile a smoke solve, cut non-algorithmic overhead
   (imports, recomputation, Python loops -> numpy), re-run battery + smoke to
   verify objectives are unchanged. Report before/after timings.
4. **Full eval**: `uv run python evaluation/eval_solver.py --problem mdkp
   --solver <file> --subset full --hypothesis-id H<k> --hypothesis "<one line>"
   --learnings "<one line incl. profiler timings>"`. This scores, updates
   `reference.json`, appends the TSV row, and resolves the hypothesis
   (status `kept`/`discarded` is decided automatically).
5. **Analyst + Researcher** (spawn both in ONE message; they may run
   concurrently - do not assume ordering): the Analyst runs
   `uv run python scripts/analyze_run.py --problem mdkp --run <ts>` (from the
   eval output line "results: runs/<ts>"), peeks into `runs/<ts>/logs/` for
   the bad instances, appends any new ideas to `ResearchDirectionsLLM.md`, and
   updates `knowledge/`. The Researcher may pre-formulate the next hypothesis
   (recorded properly at the next iteration). Both are advisory - the next
   digest re-checks the pivot state.
6. **Stop.** Bookkeeping commits and discarded-file removal are automatic
   (driver, or `scripts/finish_iteration.py` in interactive mode).

## Phase 3 - Summary (when the digest target is reached)

Write `problems/mdkp/research/report.md`: final best per-instance objectives
and their trajectory, the kept candidates in order, per-instance-class
results, the idea/hypothesis funnel (which ideas produced kept candidates),
and distilled knowledge. Then stop - run no further evaluations.

## Context economy

- The orchestrating agent should stay lean; delegate to the named agents in
  `.claude/agents/` with self-contained prompts.
- Never read `runs/*/results.json` wholesale; use the printed eval summary and
  `analyze_run.py`.
- One full eval is capped at a couple of minutes by design. Do not parallelize
  eval runs; the deterministic budget enforcement assumes sequential execution.
  (Analyst/Researcher reasoning in step 5 is fine to parallelize.)
