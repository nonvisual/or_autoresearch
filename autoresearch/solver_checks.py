"""Fast contract-level test battery for ANY solver file.

Answers "is my implementation good?" in seconds, without a full eval: the
Implementor runs the battery until it is green, then spends the smoke eval.
Checks (smoke instances, budget = max(0.5, min(TIME_BUDGETS))):

1. contract         -- module loads and defines callable solve(instance, time_budget_s).
2. feasible         -- returned solutions pass check_feasible on every smoke instance.
3. objective_bounds -- (--full, needs problems/<p>/bounds.py) objective within
                       [0, bound] for max / [bound, inf) for min; catches a
                       negated objective or a wrong sense.
4. determinism      -- two runs on the same (instance, budget): identical
                       solution, else objective within 0.1% -> WARN (not FAIL:
                       wall-clock-driven anytime designs may vary slightly).
                       Fix hint: fixed seed, iteration-count budgets.
5. budget_respect   -- wall time <= budget * SLACK on the first smoke instance.
"""

import importlib
import importlib.util
import json
import time
from dataclasses import dataclass
from pathlib import Path

from autoresearch import harness
from autoresearch.run_solver import load_solver_module

PASS, FAIL, WARN = "pass", "fail", "warn"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""


def run_battery(problem: str, solver_path: Path, repo_root: Path, full: bool = False) -> list[CheckResult]:
    solver_path = Path(solver_path)
    problem_mod = importlib.import_module(f"problems.{problem}.problem")
    evaluator = importlib.import_module(f"problems.{problem}.evaluator")
    cfg = importlib.import_module(f"problems.{problem}.benchmark_config")
    sense = getattr(cfg, "SENSE", "min")
    results: list[CheckResult] = []

    # 1. contract
    try:
        mod = load_solver_module(str(solver_path))
        results.append(CheckResult("contract", PASS, f"solve() found in {solver_path.name}"))
    except Exception as exc:  # the check itself is "does it load"
        results.append(CheckResult("contract", FAIL, f"{type(exc).__name__}: {str(exc)[-300:]}"))
        return results

    instances = [
        problem_mod.Instance.from_dict(json.loads(spec.path.read_text()))
        for spec in harness.load_instances(problem, "smoke", repo_root)
    ]
    budget = max(0.5, float(min(cfg.TIME_BUDGETS)))

    # 2. feasible (collect objectives for the bounds check)
    feasible = True
    detail: list[str] = []
    solved: list[tuple[object, object, float]] = []  # (instance, solution, objective)
    for inst in instances:
        try:
            sol = mod.solve(inst, budget)
            ok = evaluator.check_feasible(inst, sol)
            detail.append(f"feasible={ok}")
            if ok:
                solved.append((inst, sol, float(evaluator.objective(inst, sol))))
            else:
                feasible = False
        except Exception as exc:
            feasible = False
            detail.append(f"{type(exc).__name__}: {str(exc)[-120:]}")
    results.append(CheckResult("feasible", PASS if feasible else FAIL, "; ".join(detail)[:300]))

    # 3. objective bounds (--full)
    if full:
        spec = importlib.util.find_spec(f"problems.{problem}.bounds")
        if spec is None:
            results.append(CheckResult("objective_bounds", WARN, "no problems/<p>/bounds.py - skipped"))
        elif not solved:
            results.append(CheckResult("objective_bounds", FAIL, "no feasible solution to bound-check"))
        else:
            bounds_mod = importlib.import_module(f"problems.{problem}.bounds")
            ok = True
            bdetail: list[str] = []
            for inst, _sol, obj in solved:
                bnd = float(bounds_mod.bound(inst))
                good = obj <= bnd * (1 + 1e-6) if sense == "max" else obj >= bnd * (1 - 1e-6)
                ok = ok and good
                bdetail.append(f"obj {obj:.1f} vs bound {bnd:.1f}")
            results.append(CheckResult("objective_bounds", PASS if ok else FAIL,
                                       "; ".join(bdetail)[:300]))

    # 4. determinism (two runs, same instance and budget); the timed first
    #    run also feeds the budget check below, saving one extra solve
    wall_a: float | None = None
    try:
        t0 = time.perf_counter()
        a = mod.solve(instances[0], budget)
        wall_a = time.perf_counter() - t0
        b = mod.solve(instances[0], budget)
        da = a.to_dict() if hasattr(a, "to_dict") else repr(a)
        db = b.to_dict() if hasattr(b, "to_dict") else repr(b)
        if da == db:
            results.append(CheckResult("determinism", PASS, "identical solutions"))
        else:
            oa = evaluator.objective(instances[0], a) if evaluator.check_feasible(instances[0], a) else None
            ob = evaluator.objective(instances[0], b) if evaluator.check_feasible(instances[0], b) else None
            if oa is not None and ob is not None and abs(oa - ob) <= 0.001 * max(abs(oa), abs(ob), 1.0):
                results.append(CheckResult(
                    "determinism", WARN,
                    f"solutions differ, objectives close ({oa:.1f} vs {ob:.1f}); use a FIXED seed "
                    "(np.random.default_rng(<constant>)) and drive the algorithm by iteration "
                    "counts, using the time budget only as a cap",
                ))
            else:
                results.append(CheckResult(
                    "determinism", FAIL,
                    f"reruns differ materially ({oa} vs {ob}); seed all randomness from a constant",
                ))
    except Exception as exc:
        results.append(CheckResult("determinism", FAIL, f"{type(exc).__name__}: {str(exc)[-200:]}"))

    # 5. budget respect (reuses the determinism run's wall time when present)
    try:
        if wall_a is None:
            t0 = time.perf_counter()
            mod.solve(instances[0], budget)
            wall_a = time.perf_counter() - t0
        if wall_a <= budget * harness.SLACK:
            results.append(CheckResult("budget_respect", PASS, f"{wall_a:.2f}s <= {budget:g}s x {harness.SLACK}"))
        else:
            results.append(CheckResult("budget_respect", FAIL,
                                       f"{wall_a:.2f}s exceeds budget {budget:g}s (harness kills at x{harness.SLACK})"))
    except Exception as exc:
        results.append(CheckResult("budget_respect", FAIL, f"{type(exc).__name__}: {str(exc)[-200:]}"))

    return results


def summary(results: list[CheckResult]) -> str:
    lines = []
    for r in results:
        lines.append(f"{r.status.upper():4}  {r.name}: {r.detail}")
    fails = sum(1 for r in results if r.status == FAIL)
    warns = sum(1 for r in results if r.status == WARN)
    lines.append(f"battery: {len(results) - fails - warns} pass, {warns} warn, {fails} fail")
    return "\n".join(lines)


def all_pass(results: list[CheckResult]) -> bool:
    """True when nothing failed (warnings are acceptable)."""
    return all(r.status != FAIL for r in results)
