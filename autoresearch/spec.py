"""Shared types and the solver contract."""

# Run statuses that score 0.0: no feasible solution to score. Producers write
# these as plain strings ("ok" scores; everything here scores zero).
STATES_SCORED_ZERO = frozenset({"infeasible", "timeout", "error"})


class SolverContractError(Exception):
    """Raised when a solver or problem package violates the contract."""
