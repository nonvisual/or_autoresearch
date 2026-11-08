# or-autoresearch

A general MIP autoresearch loop for community reuse: an autonomous LLM research
loop that improves solvers for optimization problems on a seeded, reproducible
benchmark - measuring objective quality at each timeout. First problem: the
0-1 multidimensional knapsack (MDKP). Structure and evaluation logic descend
from `meta_autoresearch_light` (the TSP prototype); the loop protocol is
redesigned around user/LLM research ideas, a hypotheses log, named agents,
and exploration hyperparameters.

```mermaid
flowchart TD
    subgraph entry["Entry - dual usage"]
        DRV["Python driver<br/>scripts/run_loop.py<br/>autonomous, in-place (or --isolate)"]
        SKL["/or-iterate skill<br/>interactive session"]
    end
    DIG["State digest<br/>ideas, hypotheses, pivot state,<br/>history, reference, knowledge"]
    RES["Researcher agent<br/>pick idea + hypothesis<br/>pivot rule enforced"]
    IMP["Implementor agent<br/>candidate solver file"]
    BAT["Solver test battery<br/>scripts/test_solver.py<br/>+ smoke eval"]
    PRO["Profiler agent<br/>speed, behavior unchanged"]
    EV["Full eval<br/>evaluation/eval_solver.py<br/>AUC over time budgets"]
    KD{"kept / discarded<br/>reference improved?"}
    ANA["Analyst agent<br/>per-class breakdown, logs,<br/>knowledge wiki, new ideas"]
    BK["Bookkeeping<br/>commits + hypothesis resolution<br/>driver or finish_iteration.py"]
    ST[("research state<br/>ResearchDirections*.md<br/>hypotheses.tsv, history.tsv<br/>reference.json, knowledge/")]
    DRV --> DIG
    SKL --> DIG
    DIG --> RES
    RES --> IMP
    IMP --> BAT
    BAT -->|pass| PRO
    BAT -->|fail| IMP
    PRO --> EV
    EV --> KD
    KD --> ANA
    ANA --> BK
    BK --> ST
    ST --> DIG
    KD -->|next iteration| DIG
```

## Quickstart

```bash
uv sync                                                        # numpy + highspy + pytest
uv run pytest                                                  # framework + problem tests
uv run python -m problems.mdkp.generator                       # writes 9 benchmark instances
uv run python scripts/run_reference.py --problem mdkp --subset full --budgets 1,5,20,60
uv run python scripts/test_solver.py --problem mdkp \
    --solver problems/mdkp/candidates/example_random.py --full  # solver test battery
uv run python evaluation/eval_solver.py --problem mdkp \
    --solver problems/mdkp/candidates/example_random.py --subset smoke
```

Run the loop:

- **Autonomous (default, in-place)**: `uv run python scripts/run_loop.py`
  (shorthand: `uv run or-loop`; config in `loop.json`; needs `.env` with
  `ANTHROPIC_*` keys - see `.env.example`; `claude` CLI on PATH). Drives one
  headless session per iteration with a generated digest, enforces hard caps,
  prints results after every iteration plus a summary table at the end, and
  commits bookkeeping to a `loop/<problem>__<ts>` branch (created
  automatically when started from `main`; requires a clean tree).
  `--iterations N` runs N NEW full iterations (the target counts from where
  the current branch's history starts). `--dry-run` prints the plan.

  Driver artifacts (gitignored, repo root): `driver_log.jsonl` (one line per
  invocation), `.driver_prompt.txt` (the exact prompt of the last invocation),
  `.driver_state.json` (the bookkeeping checkpoint - do not delete mid-run;
  a missing checkpoint makes the next bookkeeping pass reprocess old rows).

  **`main` carries no research state** - history, hypotheses, knowledge and
  candidates live on the loop branch each run creates. Starting from `main`
  begins a fresh research line; to continue an existing one, `git checkout`
  its loop branch and run there (the driver reuses the branch and appends).
  Keep or merge loop branches as you like; `research/*` branches archive
  notable runs.
- **Autonomous (isolated)**: `uv run python scripts/run_loop.py --isolate`
  runs in a full-copy throwaway workspace under `loop_runs/` - use only to
  run several loops in parallel. `--workspace <dir>` resumes one;
  `--assemble-only` builds the workspace and stops (inspect before running).
- **Interactive**: in a Claude Code session (ideally on a branch), invoke
  `/or-iterate` (optionally `/or-iterate 3` for three iterations) - the
  session becomes the Orchestrator for one iteration and runs bookkeeping via
  `scripts/finish_iteration.py`.

Inspecting results without touching the TSVs:
`uv run python scripts/experiment_log.py [--full]` renders history.tsv joined
with hypotheses.tsv (kept list, best full score); `scripts/analyze_run.py
--run <ts>` summarizes one eval run per instance class.

## Architecture

| Piece | Path | What it is |
|---|---|---|
| Framework | `autoresearch/` | harness (fresh subprocess per instance x budget, kill at 1.25x, solver-log capture), scoring (sense-aware AUC + scorer registry), reference.json, history.tsv, hypotheses.tsv + pivot state, solver battery, digest, bookkeeping |
| Eval CLI | `evaluation/eval_solver.py` | the single evaluation entry (scores, updates reference, appends history, resolves hypotheses) |
| Problem packages | `problems/<name>/` | schema, seeded generator, evaluator, benchmark config, baselines, candidates, research state |
| Driver | `scripts/run_loop.py` + `loop.json` | autonomous mode (in-place default, `--isolate` for parallel runs), hyperparameters, per-iteration results output |
| Agents | `.claude/agents/` | implementor, profiler, analyst, researcher (the Orchestrator is the session itself) |
| Skill | `.claude/skills/or-iterate/` | interactive mode |

## Scoring

Per (instance, time budget): `0.0` if no feasible solution, else the ratio to
the best-known objective (`objective / reference_best` for maximization).
Mean across instances per budget; the mean across budgets is the AUC - i.e.
objective quality measured at each timeout, against a reference anchored with
stronger budgets. Pluggable: `--scorer <name>` selects from the registry in
`autoresearch/scoring.py`; problems can self-register scorers in
`problems/<p>/scorers.py`.

## Research state

- `problems/<p>/research/ResearchDirectionsUser.md` - your ideas (`## U1:`),
  read fresh every iteration; agents never write it.
- `problems/<p>/research/ResearchDirectionsLLM.md` - agent ideas (`## L1:`);
  combining ideas adds a new heading referencing its sources
  (`## L7 (=U2+L3): ...`).
- `problems/<p>/research/hypotheses.tsv` - every hypothesis chosen for
  experimentation: id, idea ref, type (user|llm), candidate,
  `proposed -> running -> kept | discarded`, score, rationale.
- `problems/<p>/research/knowledge/` - the Analyst's wiki of learnings.

Loop configuration lives in `loop.json` (re-read at the top of every driver
iteration, so editing it retunes a running loop):

| Key | Meaning | Consumed by |
|---|---|---|
| `problem` | problem package under `problems/` | driver, digest, CLIs |
| `iterations` | full-subset evals per run (target counts from where the current branch's history starts) | driver target, interactive digest |
| `idea_pivot_n` | consecutive discards under one idea that force a pivot (a kept result resets) | pivot rule - enforced by the driver, rendered in the digest |
| `max_hypotheses_per_idea` | hypotheses allowed under one idea before preferring a different one | digest (Researcher guidance) |
| `new_idea_every_n` | every N full iterations, nudge to propose a NEW idea | digest |
| `max_turns`, `claude_cap_minutes`, `timeout_hours` | per-invocation turn cap, hard wall-clock cap per session, overall run timeout | driver |

The scorer is NOT set here: it lives per problem in
`problems/<p>/benchmark_config.py` (`SCORER`, default `"auc"`) and can be
overridden per eval with `--scorer`.

## Candidates

A candidate is ONE file defining `solve(instance, time_budget_s) -> Solution`.
Any algorithm is allowed - MIP is not required; HiGHS (`highspy`) is available
but optional. Fixed seeds only, deterministic given (instance, budget), the
time budget is a cap. Quick feedback: `scripts/test_solver.py --problem <p>
--solver <file> [--full]` (contract, feasibility, determinism, budget
respect, objective bounds). Every eval (`eval_solver.py`) first runs a cheap
preflight - one smoke instance at the smallest budget; on `PREFLIGHT FAIL`
it exits 2 and writes nothing (no TSV row, no `runs/` dir) - fix the
candidate, do not retry. `--no-preflight` skips the check.

## Observability (Langfuse)

Detailed per-session traces - one trace per Claude Code session
(`claude_code.interaction` root, nested `claude_code.llm_request` and
`claude_code.tool` spans, prompts and tool content included) - ship to
Langfuse via Claude Code's native OTel telemetry. Opt-in, no code changes:

1. Add your keys to `.env` (see `.env.example`):
   `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and optionally
   `LANGFUSE_HOST` (default `https://cloud.langfuse.com`). Self-hosted works
   the same way - for a local instance use the official compose file
   (`docker compose up -d` from
   [langfuse/docker-compose.yml](https://github.com/langfuse/langfuse)), which
   also accepts `LANGFUSE_INIT_*` variables to bootstrap org/project/API keys
   without the UI; then set `LANGFUSE_HOST` to where it actually listens
   (e.g. `http://localhost:3300` if something else owns 3000). Budget ~4 GiB
   RAM for the stack.
2. **Autonomous driver**: nothing else. When the keys are present,
   `run_loop.py` enables telemetry for every invocation and tags its traces
   with `service.name=or-autoresearch`, `loop.problem`, `loop.workspace`, and
   `loop.iteration` - filter or group by these attributes in Langfuse to
   follow a run iteration by iteration. Each `driver_log.jsonl` entry records
   `"langfuse": true` so the audit trail knows which invocations were traced.
3. **Interactive sessions** must have the env set before `claude` starts, so
   launch through the wrapper (traces carry `loop.mode=interactive`):
   ```bash
   scripts/with_langfuse.sh claude     # then /or-iterate inside
   ```

Everything degrades gracefully: if Langfuse is not running, the driver prints
one "continuing WITHOUT tracing" notice and keeps looping (re-checking each
iteration), and `with_langfuse.sh` launches the command plainly. The one hard
failure is missing keys: `with_langfuse.sh` exits 2 when
`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are absent from `.env` (the
driver just disables telemetry in that case) - observability never blocks a
research run.

Gotcha worth knowing: Claude Code only exports OTLP **traces** when both
`CLAUDE_CODE_ENABLE_TELEMETRY=1` and `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`
are set - without the beta flag it emits only log records, which self-hosted
Langfuse v4 cannot ingest (no `/v1/logs` route). The driver and the wrapper
set this for you; the `/langfuse` skill documents verification and
troubleshooting. To correlate a trace with the on-disk loop state, match
`loop.workspace` + `loop.iteration` against the workspace's
`.driver_prompt.txt` and `driver_log.jsonl`.

### Cost tracking

Langfuse's token/cost columns stay empty for Claude Code sessions for now
(Claude Code emits plain `input_tokens`/`output_tokens` attribute names;
Langfuse waits for `gen_ai.usage.*`). For cost visibility today, use a local
tool that reads Claude Code's own session data instead - no exporter involved:

- [CodeBurn](https://github.com/getagentseal/codeburn) - free, fully local
  CLI; prices every call (input/output/cache/web-search tokens) from
  LiteLLM rates refreshed daily; tracks 37+ coding tools including Claude
  Code.
- [AgentsView](https://agentsview.io) - local viewer for what each agent
  session did and what it cost: file edits, tool calls, child sessions,
  per-tool/model breakdowns, cache economics; ships read-only MCP tools.

Both pair well with Langfuse: traces there, money here.

## Adding a problem

```bash
uv run python scripts/new_problem.py --name binpacking
```

Implement the five files under `problems/binpacking/` (see
`problems/_template/README.md`): `problem.py` (Instance/Solution with JSON
round-trip + aliases), `generator.py` (seeded, feasible by construction),
`evaluator.py` (feasibility + objective), `benchmark_config.py`
(INSTANCE_CLASSES / TIME_BUDGETS / SUBSETS with a tiny smoke set, plus `SENSE`
and optional `SCORER`), and `solvers/` (a strong anchor + an always-feasible
constructive baseline). Optional hooks: `bounds.py` (bound for the battery's
`--full` check) and `scorers.py` (custom scorers). Then generate instances,
build the reference with STRONGER budgets than `TIME_BUDGETS` (e.g.
`--budgets 1,5,20,60` for eval budgets `[1, 5]` - a strong anchor keeps ratio
scores meaningful), and point `loop.json`'s `"problem"` at it.

## Conventions

uv only (never pip), conventional commits (`feat:`/`fix:`/`refactor:`/`docs:`/`chore:`),
tests via `uv run pytest`, no emojis, benchmark instances are read-only.
