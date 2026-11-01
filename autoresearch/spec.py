"""Shared types and the solver contract."""

from dataclasses import dataclass
from enum import Enum


class ResultStatus(str, Enum):
    OK = "ok"
    INFEASIBLE = "infeasible"
    TIMEOUT = "timeout"
    ERROR = "error"


STATES_SCORED_ZERO = {ResultStatus.INFEASIBLE, ResultStatus.TIMEOUT, ResultStatus.ERROR}


class SolverContractError(Exception):
    """Raised when a solver or problem package violates the contract."""


@dataclass(frozen=True)
class SolverContract:
    """What every solver file must provide."""

    entry_point: str = "solve"           # solve(instance, time_budget_s) -> Solution
    solution_needs: str = "to_dict()"    # JSON-serializable payload
    time_budget_s: str = "wall-clock seconds the solver may use; harness kills hard at budget * SLACK"
