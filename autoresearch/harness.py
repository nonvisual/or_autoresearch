"""Evaluation harness: run a solver across (instance, budget) pairs in fresh subprocesses.

Deterministic and isolated: every run gets a brand-new process, so there is no
warm state, and overruns are enforced by a hard kill at ``budget * SLACK``.
When ``log_dir`` is set, solver diagnostics (stderr plus any stdout beyond the
final JSON line) are archived per run into ``log_dir/<instance>_<budget>s.log``
and each row carries ``log`` (path, "" if none) and ``log_tail`` (last 500
chars of stderr) - the Analyst's feed.
"""

import importlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SLACK = 1.25


@dataclass(frozen=True)
class InstanceSpec:
    name: str
    path: Path


def load_instances(problem: str, subset: str, repo_root: Path) -> list[InstanceSpec]:
    """Resolve a named subset from the problem's benchmark_config into instance files."""
    cfg = importlib.import_module(f"problems.{problem}.benchmark_config")
    wanted = cfg.SUBSETS[subset]
    bench_dir = repo_root / "problems" / problem / "benchmark"
    specs: list[InstanceSpec] = []
    for class_name, params in cfg.INSTANCE_CLASSES.items():
        for seed in params["seeds"]:
            name = f"{class_name}_{seed}"
            if name in wanted:
                path = bench_dir / f"{name}.json"
                if not path.exists():
                    raise FileNotFoundError(
                        f"{path} missing - run: uv run python -m problems.{problem}.generator"
                    )
                specs.append(InstanceSpec(name, path))
    missing = set(wanted) - {s.name for s in specs}
    if missing:
        raise ValueError(f"subset '{subset}' references unknown instances: {sorted(missing)}")
    return specs


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def _attach_log(row: dict, log_dir: Path | None, instance_path: Path, budget: float,
                extra_stdout: str, stderr: str) -> None:
    tail = (stderr or "")[-500:]
    row["log_tail"] = tail
    row["log"] = ""
    if log_dir is None or not (stderr or extra_stdout):
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{instance_path.stem}_{budget:g}s.log"
    parts = []
    if extra_stdout:
        parts.append("--- solver stdout (beyond the JSON payload) ---\n" + extra_stdout)
    if stderr:
        parts.append("--- solver stderr ---\n" + stderr)
    path.write_text("\n".join(parts) + "\n")
    row["log"] = str(path)


def run_single(
    problem: str,
    solver_path: Path,
    instance_path: Path,
    budget: float,
    repo_root: Path,
    slack: float = SLACK,
    log_dir: Path | None = None,
) -> dict:
    """One (solver, instance, budget) run in a fresh subprocess."""
    cmd = [
        sys.executable,
        "-m",
        "autoresearch.run_solver",
        "--problem",
        problem,
        "--solver",
        str(solver_path.resolve()),
        "--instance",
        str(instance_path.resolve()),
        "--budget",
        repr(float(budget)),
    ]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=budget * slack,
            cwd=repo_root,
        )
    except subprocess.TimeoutExpired as exc:
        row = {
            "status": "timeout",
            "objective": None,
            "solution": None,
            "detail": f"killed at budget*{slack} ({budget * slack:.2f}s)",
        }
        _attach_log(row, log_dir, instance_path, budget, "", _as_text(exc.stderr))
        return row
    wall_s = time.perf_counter() - t0
    stderr_text = proc.stderr or ""
    stdout_lines = proc.stdout.strip().splitlines() if proc.stdout else []
    extra_stdout = "\n".join(stdout_lines[:-1]) if stdout_lines else ""

    if proc.returncode != 0:
        row = {
            "status": "error",
            "objective": None,
            "solution": None,
            "wall_s": wall_s,
            "detail": stderr_text[-4000:],
        }
        _attach_log(row, log_dir, instance_path, budget, extra_stdout, stderr_text)
        return row
    try:
        payload = json.loads(stdout_lines[-1])
    except (json.JSONDecodeError, IndexError):
        row = {
            "status": "error",
            "objective": None,
            "solution": None,
            "wall_s": wall_s,
            "detail": f"unparseable solver output: {proc.stdout[-500:]}",
        }
        _attach_log(row, log_dir, instance_path, budget, extra_stdout, stderr_text)
        return row
    payload["wall_s"] = wall_s
    _attach_log(payload, log_dir, instance_path, budget, extra_stdout, stderr_text)
    return payload


def evaluate(
    problem: str,
    solver_path: Path,
    instances: list[InstanceSpec],
    budgets: list[float],
    repo_root: Path,
    log_dir: Path | None = None,
) -> list[dict]:
    """Run every (instance, budget) pair sequentially. Returns raw result rows."""
    rows: list[dict] = []
    for budget in budgets:
        for inst in instances:
            res = run_single(problem, solver_path, inst.path, budget, repo_root, log_dir=log_dir)
            res.update(
                {
                    "instance": inst.name,
                    "budget": float(budget),
                    "solver": Path(solver_path).name,
                }
            )
            rows.append(res)
    return rows
