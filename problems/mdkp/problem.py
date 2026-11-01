"""MDKP schema: instance and solution dataclasses (JSON round-trip)."""

from dataclasses import dataclass


@dataclass
class MDKPInstance:
    n: int                     # items, j in range(n)
    m: int                     # capacity dimensions, i in range(m)
    values: list[int]          # profit p_j >= 0 of item j
    weights: list[list[int]]   # w[i][j] > 0: consumption of item j in dimension i (m x n)
    capacities: list[int]      # c_i > 0

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "m": self.m,
            "values": list(self.values),
            "weights": [list(row) for row in self.weights],
            "capacities": list(self.capacities),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MDKPInstance":
        n = int(d["n"])
        m = int(d["m"])
        values = [int(v) for v in d["values"]]
        weights = [[int(w) for w in row] for row in d["weights"]]
        capacities = [int(c) for c in d["capacities"]]
        if n <= 0 or m <= 0:
            raise ValueError(f"n and m must be positive, got n={n} m={m}")
        if len(values) != n:
            raise ValueError(f"values has {len(values)} entries, expected n={n}")
        if len(weights) != m or any(len(row) != n for row in weights):
            raise ValueError(f"weights must be m x n = {m} x {n}")
        if len(capacities) != m:
            raise ValueError(f"capacities has {len(capacities)} entries, expected m={m}")
        if any(c <= 0 for c in capacities):
            raise ValueError("capacities must be positive")
        return cls(n=n, m=m, values=values, weights=weights, capacities=capacities)


@dataclass
class MDKPSolution:
    selected: list[int]        # chosen item indices, distinct (conventionally sorted)

    def to_dict(self) -> dict:
        return {"selected": list(self.selected)}

    @classmethod
    def from_dict(cls, d: dict) -> "MDKPSolution":
        return cls(selected=[int(j) for j in d["selected"]])


# The framework's import points (problems.mdkp.problem.Instance / .Solution).
Instance = MDKPInstance
Solution = MDKPSolution
