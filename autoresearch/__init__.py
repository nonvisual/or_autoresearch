"""Problem-agnostic auto-research framework.

A *problem package* lives at ``problems/<name>/`` and must expose:

- ``problem.py``      -- ``Instance`` and ``Solution`` dataclasses with
                        ``to_dict()`` / ``from_dict()`` (JSON round-trip).
- ``generator.py``    -- seeded instance generation, feasible by construction;
                        runnable as ``python -m problems.<name>.generator``
                        to write ``benchmark/``.
- ``evaluator.py``    -- ``check_feasible(instance, solution) -> bool`` and
                        ``objective(instance, solution) -> float`` (independent of any solver).
- ``benchmark_config.py`` -- ``INSTANCE_CLASSES``, ``TIME_BUDGETS``, ``SUBSETS``;
                        optionally ``SENSE`` ("min"|"max", default "min") and
                        ``SCORER`` (registry key, default "auc").
- ``solvers/``        -- reference solvers (at least one correct baseline;
                        at least one must be feasible on every instance).
- ``candidates/``     -- candidate solvers produced by the research loop.

Optional hooks (both imported only when present):

- ``problems/<name>/bounds.py``    -- ``bound(instance) -> float``: best-possible
  objective bound in the problem's sense (upper bound for max, lower for min).
  Used by the solver test battery (``--full``), never by the eval subprocess.
- ``problems/<name>/scorers.py``   -- problem-local scorers that self-register
  via ``autoresearch.scoring.register`` on import.

Solver contract: a solver file defines ``solve(instance, time_budget_s) -> Solution``.
Any algorithm is allowed - MIP is NOT required.
"""

from autoresearch.spec import SolverContractError
from autoresearch import harness, hypotheses, reference, tsv

__all__ = [
    "SolverContractError",
    "harness",
    "hypotheses",
    "reference",
    "tsv",
]
