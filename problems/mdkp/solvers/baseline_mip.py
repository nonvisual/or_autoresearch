"""Reference solver: exact MIP via HiGHS - the strong anchor.

Builds the MDKP directly through the low-level ``passModel`` interface (fast
even at n=500): one binary column per item, one <= row per dimension,
maximize total profit. x = 0 is feasible, so a time-limited run always has an
incumbent to return. This is the one place where HiGHS is used as a SOLVER;
candidates may use any algorithm.
"""

import numpy as np
import highspy

from problems.mdkp.problem import MDKPSolution


def build_lp(instance) -> highspy.HighsLp:
    """The MDKP linear model, continuous (integrality added by the MIP solver)."""
    n, m = instance.n, instance.m
    lp = highspy.HighsLp()
    lp.num_col_ = n
    lp.num_row_ = m
    lp.col_cost_ = np.asarray(instance.values, dtype=np.double)
    lp.col_lower_ = np.zeros(n)
    lp.col_upper_ = np.ones(n)
    lp.row_lower_ = np.full(m, -highspy.kHighsInf)
    lp.row_upper_ = np.asarray(instance.capacities, dtype=np.double)
    # column-wise sparse matrix: column j holds w[i][j] for every row i
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_ = np.arange(n + 1, dtype=np.int32) * m
    lp.a_matrix_.index_ = np.tile(np.arange(m, dtype=np.int32), n)
    lp.a_matrix_.value_ = np.asarray(instance.weights, dtype=np.double).T.ravel()
    lp.sense_ = highspy.ObjSense.kMaximize
    return lp


def solve(instance, time_budget_s):
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", max(0.2, 0.9 * float(time_budget_s)))
    h.setOptionValue("mip_rel_gap", 0.0)

    lp = build_lp(instance)
    lp.integrality_ = np.full(instance.n, highspy.HighsVarType.kInteger)  # binary via [0,1]
    h.passModel(lp)
    h.run()

    x = list(h.getSolution().col_value)
    if len(x) != instance.n:
        raise RuntimeError(
            f"HiGHS returned no solution ({h.modelStatusToString(h.getModelStatus())})"
        )
    return MDKPSolution(sorted(j for j in range(instance.n) if x[j] > 0.5))
