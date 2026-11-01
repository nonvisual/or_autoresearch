"""Scoring: pluggable scorers over raw harness rows, sense-aware.

The default ``"auc"`` scorer reproduces the meta_autoresearch_light logic -
objective quality at each timeout - as a ratio against the current reference:

- per (instance, budget): ``0.0`` if the run produced no feasible solution, else
  ``reference_best / objective`` for minimization (``SENSE_MIN``) and
  ``objective / reference_best`` for maximization (``SENSE_MAX``). Above 1.0
  means the run beat the current reference in both senses.
- mean across instances per budget, then the mean across budgets is the AUC.

Scorers are a registry: ``@register("name")`` on ``fn(rows, reference, sense)
-> dict``; every scorer must expose a scalar ``"score"`` key. Problem-local
scorers live in ``problems/<name>/scorers.py`` and self-register on import
(eval_solver imports that module when it exists). Selection precedence:
CLI ``--scorer`` > ``benchmark_config.SCORER`` > ``"auc"``.
"""

from typing import Callable

from autoresearch.spec import STATES_SCORED_ZERO

SENSE_MIN = "min"
SENSE_MAX = "max"


def instance_score(reference_best: float, objective: float, sense: str = SENSE_MIN) -> float:
    if sense == SENSE_MAX:
        if reference_best <= 0:
            raise ValueError(f"reference must be positive, got {reference_best}")
        if objective < 0:
            raise ValueError(f"objective must be non-negative, got {objective}")
        return objective / reference_best
    if objective <= 0:
        raise ValueError(f"objective must be positive, got {objective}")
    return reference_best / objective


def is_better(new: float, old: float, sense: str = SENSE_MIN) -> bool:
    """Strict improvement in the given sense (used by reference.update et al.)."""
    return new > old if sense == SENSE_MAX else new < old


def score_rows(rows: list[dict], reference: dict[str, float], sense: str = SENSE_MIN) -> dict:
    """Score raw harness rows against ``{instance_name: reference_objective}``."""
    budgets = sorted({r["budget"] for r in rows})
    per_budget: dict[float, float] = {}
    for b in budgets:
        b_rows = [r for r in rows if r["budget"] == b]
        scores = []
        for r in b_rows:
            if r["status"] in {s.value for s in STATES_SCORED_ZERO}:
                scores.append(0.0)
            else:
                scores.append(instance_score(reference[r["instance"]], r["objective"], sense))
        per_budget[b] = sum(scores) / len(scores)
    auc = sum(per_budget.values()) / len(per_budget) if per_budget else 0.0
    return {"per_budget": per_budget, "auc": auc, "coverage": coverage(rows)}


def coverage(rows: list[dict]) -> float:
    """Fraction of runs that produced a feasible solution."""
    if not rows:
        return 0.0
    ok = sum(1 for r in rows if r["status"] == "ok")
    return ok / len(rows)


def best_objectives(rows: list[dict], sense: str = SENSE_MIN) -> dict[str, float]:
    """Best feasible objective found per instance across all budgets."""
    best: dict[str, float] = {}
    for r in rows:
        if r["status"] == "ok":
            name = r["instance"]
            cur = best.get(name)
            if cur is None or is_better(r["objective"], cur, sense):
                best[name] = r["objective"]
    return best


ScorerFn = Callable[[list[dict], dict[str, float], str], dict]
_SCORERS: dict[str, ScorerFn] = {}


def register(name: str) -> Callable[[ScorerFn], ScorerFn]:
    """Decorator: register a scorer ``fn(rows, reference, sense) -> dict``."""

    def deco(fn: ScorerFn) -> ScorerFn:
        _SCORERS[name] = fn
        return fn

    return deco


def get(name: str) -> ScorerFn:
    try:
        return _SCORERS[name]
    except KeyError:
        raise ValueError(f"unknown scorer '{name}' (known: {sorted(_SCORERS)})") from None


def run(name: str, rows: list[dict], reference: dict[str, float], sense: str) -> dict:
    """Run a registered scorer; the result always carries "scorer" and "score"."""
    out = dict(get(name)(rows, reference, sense))
    if "score" not in out:
        raise ValueError(f"scorer '{name}' must expose a scalar 'score' key")
    out["scorer"] = name
    return out


@register("auc")
def _auc(rows: list[dict], reference: dict[str, float], sense: str) -> dict:
    s = score_rows(rows, reference, sense)
    return {
        "score": s["auc"],
        "auc": s["auc"],
        "per_budget": s["per_budget"],
        "coverage": s["coverage"],
    }
