"""MDKP feasibility and objective - independent of any solver."""


def check_feasible(instance, solution) -> bool:
    sel = solution.selected
    if len(set(sel)) != len(sel):
        return False
    for j in sel:
        if not 0 <= j < instance.n:
            return False
    for i in range(instance.m):
        row = instance.weights[i]
        cap = instance.capacities[i]
        if sum(row[j] for j in sel) > cap:
            return False
    return True


def objective(instance, solution) -> float:
    """Total profit of the selected items (MAXIMIZATION)."""
    return float(sum(instance.values[j] for j in solution.selected))
