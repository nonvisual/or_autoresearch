# or-autoresearch

An autonomous research loop improving solvers for optimization problems
(currently `mdkp`, 0-1 multidimensional knapsack). For any research task, read
and follow `AGENTS.md` - it is the protocol.

## Rules

- Tooling: uv only, never pip (`uv sync`, `uv run ...`).
- `problems/*/benchmark/` is read-only for research; regenerate only via the
  problem's generator with committed seeds.
- Every evaluation runs through `uv run python evaluation/eval_solver.py --problem mdkp`
  with `--hypothesis-id`/`--hypothesis`/`--learnings`; it appends `history.tsv`,
  resolves the hypothesis in `hypotheses.tsv`, and updates `reference.json`.
  Never hand-edit any of them.
- Every candidate passes `scripts/test_solver.py` (battery) and `--subset smoke`
  before `--subset full`. One full-subset eval per invocation.
- `problems/*/research/ResearchDirectionsUser.md` belongs to the human owner:
  read it, never write it. Agents contribute ideas to `ResearchDirectionsLLM.md`.
- Bookkeeping is AUTOMATIC (driver, or `scripts/finish_iteration.py` in
  interactive mode). Do not run git, do not delete candidate files.
- Respect the digest: honor `PIVOT REQUIRED` and the loop hyperparameters it states.
- Candidates respect `time_budget_s` (fixed seeds, budget as a cap); the
  harness kills overruns (score 0).
- At the target number of `full` rows (from the digest): write
  `problems/mdkp/research/report.md` and stop - no more evals.
- No emojis.
