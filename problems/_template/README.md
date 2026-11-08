# Problem package: `<name>`

Implement these five files (stubs raise `NotImplementedError`):

1. **`problem.py`** - `XInstance` / `XSolution` dataclasses with `to_dict()` /
   `from_dict()` (JSON round-trip) and module-level aliases
   `Instance = XInstance`, `Solution = XSolution` (the framework's import points).
2. **`generator.py`** - `make_instance(...)` seeded and feasible by
   construction; `python -m problems.<name>.generator` writes
   `benchmark/<class>_<seed>.json` for every configured class.
3. **`evaluator.py`** - `check_feasible(instance, solution) -> bool` and
   `objective(instance, solution) -> float`, independent of any solver.
4. **`benchmark_config.py`** - `PROBLEM`, `INSTANCE_CLASSES` (name -> params
   incl. `seeds`), `TIME_BUDGETS`, `SUBSETS` (must include a tiny `smoke` and
   `full`); optionally `SENSE` (`"min"` default or `"max"`) and `SCORER`
   (registry key, default `"auc"`).
5. **`solvers/`** - at least two reference solvers: a strong anchor
   (`baseline_strong.py`) and an always-feasible constructive one
   (`baseline_constructive.py`) so `run_reference.py` can anchor every instance.

Optional hooks (imported only when present):

- **`bounds.py`** - `bound(instance) -> float`: best-possible objective bound
  in the problem's sense (upper bound for max, lower for min). Enables the
  `--full` objective-bounds check in `scripts/test_solver.py`.
- **`scorers.py`** - problem-local scorers registered via
  `from autoresearch.scoring import register` + `@register("name")`.

The solver contract (candidates and baselines alike): ONE file defining
`solve(instance, time_budget_s) -> Solution`. Any algorithm is allowed.

`research/` is the loop's state (seeded here, written by the loop):
`ResearchDirectionsUser.md` (human ideas, `## U1:` headings),
`ResearchDirectionsLLM.md` (agent ideas, `## L1:` headings; combined ideas
reference sources, e.g. `## L7 (=U2+L3):`), `hypotheses.tsv`,
`history.tsv`, `knowledge/`, `notes/`.

## Checklist

- [ ] implement the five files above
- [ ] `uv run python -m problems.<name>.generator`
- [ ] `uv run python scripts/run_reference.py --problem <name> --subset full --budgets <stronger than TIME_BUDGETS>`
      (stronger reference budgets anchor the ratio scores - see the header of
      `scripts/run_reference.py`)
- [ ] set `"problem": "<name>"` in loop.json
- [ ] `uv run python scripts/run_loop.py --dry-run`
