"""Optional bound hook: LP relaxation optimum of the MDKP (upper bound for max).

Used only by the solver test battery (``--full``) and by analysis tooling;
never imported in the eval subprocess path. ``bound(instance)`` follows the
framework convention: best-possible objective bound in the problem's sense.
"""

import numpy as np
import highspy

from problems.mdkp.solvers.baseline_mip import build_lp


def bound(instance) -> float:
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", 10.0)
    h.passModel(build_lp(instance))  # continuous relaxation: no integrality_
    h.run()
    return float(h.getObjectiveValue())
