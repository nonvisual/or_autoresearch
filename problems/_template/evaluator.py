"""Feasibility + objective stub, independent of any solver."""


def check_feasible(instance, solution) -> bool:
    raise NotImplementedError


def objective(instance, solution) -> float:
    raise NotImplementedError
