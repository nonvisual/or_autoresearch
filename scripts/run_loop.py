"""Run the autoresearch loop autonomously, end-to-end.

    uv run python scripts/run_loop.py                       # IN-PLACE (default)
    uv run python scripts/run_loop.py --iterations 2        # in-place, 2 iterations
    uv run python scripts/run_loop.py --dry-run             # print the plan, change nothing
    uv run python scripts/run_loop.py --isolate             # full-copy workspace (parallel-safe)
    uv run python scripts/run_loop.py --workspace <ws>      # resume an isolate-mode workspace

IN-PLACE (default): the loop runs directly on this repo - sessions get the
repo as cwd, evaluations and bookkeeping commit to a dedicated branch
(loop/<problem>__<ts>, created automatically when started from main/master;
the tree must be clean). Research state (history.tsv, hypotheses, reference,
candidates) lives in the repo, so results are never trapped in a copy.

ISOLATE (--isolate): assembles a full-copy workspace under
loop_runs/<problem>__<UTC ts>/ (parallel-safe, throwaway git history). Use it
only to run several loops concurrently.

Configuration comes from the repo-root loop.json (problem, iterations, loop
hyperparameters like idea_pivot_n, per-invocation caps); CLI flags override.
The config is RE-READ at the top of every iteration, so editing loop.json
retunes a running loop. Invocations are headless `claude -p` sessions driven
by a generated state digest, hard-capped (process-group kill) so nothing
outlives the driver; results are printed after every iteration and summarized
at the end. In isolate mode the user's ResearchDirectionsUser.md is synced
host -> workspace before each invocation (agents never write it).
"""

import argparse
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autoresearch import bookkeeping, digest, hypotheses, tsv  # noqa: E402
from autoresearch.config import load_config, hyper_of  # noqa: E402
from autoresearch.tsv import count_full  # noqa: E402
from autoresearch.textutil import one_line  # noqa: E402

RSYNC_EXCLUDES = [
    ".git", ".venv", "__pycache__", ".pytest_cache", ".DS_Store",
    "loop_runs", "runs", ".env",
    ".driver_prompt.txt", ".driver_state.json", "driver_log.jsonl", ".claude-config",
    ".claude/settings.local.json", ".claude/scheduled_tasks.lock",
]

DEFAULT_MAX_TURNS = 60
DEFAULT_CLAUDE_CAP_MINUTES = 20.0
DEFAULT_TIMEOUT_HOURS = 12.0
KILL_GRACE_S = 30

ENV_PREFIXES = ("ANTHROPIC_", "CLAUDE_", "LANGFUSE_", "OTEL_")


def load_env_config(env_path: Path = REPO_ROOT / ".env") -> dict[str, str]:
    """Pull the LLM + observability config (ANTHROPIC_*/CLAUDE_*/LANGFUSE_*/OTEL_*) out of .env."""
    config: dict[str, str] = {}
    if not env_path.is_file():
        return config
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith(ENV_PREFIXES):
            config[key] = value.strip().strip("'\"")
    return config


def langfuse_config(env_config: dict[str, str]) -> dict | None:
    """Langfuse connection from .env-style config; None disables telemetry (pure)."""
    public_key = env_config.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = env_config.get("LANGFUSE_SECRET_KEY", "")
    if not (public_key and secret_key):
        return None
    host = (env_config.get("LANGFUSE_HOST") or "https://cloud.langfuse.com").rstrip("/")
    return {"public_key": public_key, "secret_key": secret_key, "host": host}


def langfuse_reachable(langfuse: dict, timeout_s: float = 2.0) -> bool:
    """True if the Langfuse service answers at all (any HTTP status counts).

    Telemetry is strictly fire-and-forget: when the service is down the loop
    continues WITHOUT tracing - observability must never fail a research run.
    """
    try:
        urllib.request.urlopen(f"{langfuse['host']}/api/public/health", timeout=timeout_s)
        return True
    except urllib.error.HTTPError:
        return True  # service answered (auth/routing); the exporter gets the same
    except Exception:  # noqa: BLE001 - connection refused, timeout, DNS: all "down"
        return False


def telemetry_env(langfuse: dict | None, attributes: dict[str, str]) -> dict[str, str]:
    """OTel env vars routing Claude Code's native session telemetry to Langfuse (pure).

    Claude Code exports OTLP traces - one trace per session
    (claude_code.interaction) with nested llm_request / tool spans - only when
    BOTH CLAUDE_CODE_ENABLE_TELEMETRY=1 AND CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
    are set; without the beta flag it only emits log records (which self-hosted
    Langfuse v4 cannot ingest - no /v1/logs route). The DETAILED tier
    (ENABLE_BETA_TRACING_DETAILED=1 + BETA_TRACING_ENDPOINT) additionally puts
    content ON the spans - user_prompt on interaction, response.model_output on
    llm_request, tool_input on tool spans - and redirects trace/log export to
    that endpoint (http/json, which Langfuse accepts). Metrics/logs exporters
    stay "none": Langfuse takes traces only. The 1s export interval flushes
    short sessions. The resource attributes tag every span with loop context
    (filterable in Langfuse).
    """
    if langfuse is None:
        return {}
    token = base64.b64encode(
        f"{langfuse['public_key']}:{langfuse['secret_key']}".encode()
    ).decode()
    attrs = ",".join(f"{k}={v}" for k, v in sorted(attributes.items()))
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "ENABLE_BETA_TRACING_DETAILED": "1",
        "BETA_TRACING_ENDPOINT": f"{langfuse['host']}/api/public/otel",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_ENDPOINT": f"{langfuse['host']}/api/public/otel",
        "OTEL_EXPORTER_OTLP_HEADERS": f"Authorization=Basic {token}",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "none",
        "OTEL_TRACES_EXPORT_INTERVAL": "1000",
        "OTEL_LOG_USER_PROMPTS": "1",
        "OTEL_LOG_TOOL_DETAILS": "1",
        "OTEL_LOG_TOOL_CONTENT": "1",
        "OTEL_RESOURCE_ATTRIBUTES": attrs,
    }


def session_env(ws: Path, env_config: dict[str, str],
                telemetry: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a claude invocation: host env + .env config + optional
    telemetry vars + isolated config dir."""
    env = dict(os.environ)
    env.update(env_config)
    if telemetry:
        env.update(telemetry)
    config_dir = ws / ".claude-config"
    config_dir.mkdir(exist_ok=True)
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return env


def claude_command(max_turns: int) -> list[str]:
    """The headless claude invocation (pure; unit-tested)."""
    return [
        "claude", "--dangerously-skip-permissions", "-p",
        "--max-turns", str(max_turns),
        "--output-format", "stream-json", "--verbose",
    ]


def _shorten(text: str, limit: int = 70) -> str:
    return one_line(text, limit)


def format_event(line: str) -> str | None:
    """One compact progress line from a stream-json event, or None to stay quiet.

    Tool calls show as ``[claude] Bash(uv run python ...)``; the closing result
    event shows turn count and duration. Anything else is suppressed.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    etype = event.get("type")
    if etype == "assistant":
        parts = []
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "tool_use":
                hint = next(
                    (str(v) for v in block.get("input", {}).values()
                     if isinstance(v, (str, int, float))),
                    "",
                )
                parts.append(f"{block.get('name', '?')}({_shorten(hint, 50)})")
            elif block.get("type") == "text" and str(block.get("text", "")).strip():
                parts.append(_shorten(block["text"], 90))
        return f"[claude] {' | '.join(parts)}" if parts else None
    if etype == "result":
        secs = float(event.get("duration_ms", 0)) / 1000
        return (f"[claude] session finished: {event.get('subtype', '?')}, "
                f"{event.get('num_turns', '?')} turns, {secs:.0f}s")
    return None


def summarize_rows(rows: list[dict]) -> str:
    """One line per full-subset eval - the driver's results log (pure; unit-tested)."""
    lines = []
    for r in rows:
        lines.append(
            f"  #{r.get('iteration', '?'):>3}  {r.get('candidate_file', '?'):36} "
            f"score {r.get('score') or '-':>9}  cov {r.get('coverage') or '-':>6}  "
            f"{r.get('status', '?'):9}  {_shorten(r.get('hypothesis'), 50)}"
        )
    return "\n".join(lines)


def build_iteration_prompt(digest_text: str, iteration_no: int, total: int,
                           must_pivot: bool = False) -> str:
    """The per-invocation driver prompt (pure; unit-tested)."""
    pivot = ""
    if must_pivot:
        pivot = (
            "\nCONSTRAINT: the current idea has exhausted its pivot budget - the "
            "Researcher must select or propose a DIFFERENT idea (see digest).\n"
        )
    return (
        f"Iteration {iteration_no}/{total}. The state digest below is driver-generated "
        "and current - TRUST IT and do NOT re-read history.tsv, hypotheses.tsv, "
        "reference.json, or the ResearchDirections files this session.\n\n"
        f"{digest_text}\n{pivot}\n"
        "Perform exactly ONE full iteration per AGENTS.md Phase 2 (Researcher -> "
        "Implementor -> battery/smoke -> Profiler -> full eval -> Analyst/Researcher), "
        "then STOP. Bookkeeping is AUTOMATIC: do not run git commit, do not delete "
        "candidate files, do not edit ResearchDirectionsUser.md, and do not hand-edit "
        "history.tsv or hypotheses.tsv (the CLIs write them)."
    )


def assemble_workspace(ws: Path, root: Path = REPO_ROOT) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-a"]
    for exc in RSYNC_EXCLUDES:
        cmd += ["--exclude", exc]
    source = str(root).rstrip("/") + "/"
    cmd += [source, str(ws) + "/"]
    subprocess.run(cmd, check=True)


def sync_user_directions(host_problem_dir: Path, ws_problem_dir: Path) -> bool:
    """One-way host -> workspace copy of the user's idea file (pure; unit-tested).

    Agents never write ResearchDirectionsUser.md, so no reverse sync is needed.
    In-place mode passes the same directory twice - a no-op.
    """
    src = hypotheses.user_directions_path(host_problem_dir)
    if not src.is_file():
        return False
    dst = hypotheses.user_directions_path(ws_problem_dir)
    if src.resolve() == dst.resolve():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def init_git(ws: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(ws), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "loop@or-autoresearch")
    git("config", "user.name", f"loop-{ws.name}")
    git("add", "-A")
    git("commit", "-q", "-m", "init: assembled loop workspace")


def _kill_group(proc: subprocess.Popen, grace_s: int = KILL_GRACE_S) -> None:
    """Terminate the process group (claude + subagents): TERM, grace, KILL."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(grace_s):
        if proc.poll() is not None:
            return
        time.sleep(1)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def run_claude(ws: Path, cmd: list[str], prompt: str, cap_minutes: float, env: dict) -> tuple:
    """One headless invocation with a hard wall-clock cap.

    Prints ``[claude] ...`` progress lines as stream-json events arrive.
    Returns (rc, timed_out, wall_s).
    """
    t0 = time.monotonic()
    timed_out = False
    proc = subprocess.Popen(
        cmd, cwd=str(ws), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        env=env, start_new_session=True, text=True,
    )

    def _feed() -> None:
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except (BrokenPipeError, ValueError):
            pass

    def _read() -> None:
        for line in proc.stdout:
            rendered = format_event(line)
            if rendered:
                print(rendered, flush=True)

    threading.Thread(target=_feed, daemon=True).start()
    reader = threading.Thread(target=_read, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=cap_minutes * 60)
    except subprocess.TimeoutExpired:
        timed_out = True
        print(f"[driver] invocation exceeded {cap_minutes:.0f} min - killing process group")
        _kill_group(proc)
        proc.wait()
    reader.join(timeout=5)
    wall_s = time.monotonic() - t0
    return proc.returncode, timed_out, wall_s


def _log_invocation(ws: Path, **entry) -> None:
    record = {
        "invoked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **entry,
    }
    with (ws / "driver_log.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")


def run_driver(ws: Path, problem: str, iterations: int, timeout_hours: float,
               max_turns: int, claude_cap_minutes: float) -> None:
    problem_dir = ws / "problems" / problem
    host_problem_dir = REPO_ROOT / "problems" / problem
    deadline = time.monotonic() + timeout_hours * 3600
    stalled = 0
    # iterations counts NEW full-subset rows for THIS run; history.tsv carries
    # every past run's rows (in-place mode), so the target is start_rows + N.
    start_rows = count_full(problem_dir)
    target_rows = start_rows + iterations
    prev_rows = start_rows
    env_config = load_env_config()
    langfuse = langfuse_config(env_config)
    telemetry_down_notice = False
    cmd = claude_command(max_turns)
    print(f"[driver] {start_rows} historical full iterations; running {iterations} more "
          f"(target {target_rows})")

    while prev_rows < target_rows and time.monotonic() < deadline:
        cfg = load_config(REPO_ROOT)  # host config, re-read every iteration
        hyper = hyper_of(cfg)
        sync_user_directions(host_problem_dir, problem_dir)

        done = prev_rows - start_rows  # this run's completed iterations
        pivot = hypotheses.pivot_state(problem_dir, int(hyper.get("idea_pivot_n", 3)))
        digest_text = digest.build(problem_dir, target_rows, hyper, pivot=pivot)
        prompt = build_iteration_prompt(
            digest_text, done + 1, iterations, must_pivot=pivot["must_pivot"]
        )
        # Env is rebuilt per iteration so every session's traces carry the
        # current loop context (workspace, iteration number) as attributes.
        # If Langfuse is down, telemetry is skipped (never fatal); the check
        # re-runs each iteration, so starting the stack mid-run re-enables it.
        live = langfuse is not None and langfuse_reachable(langfuse)
        if langfuse is not None:
            if not live and not telemetry_down_notice:
                print(f"[driver] telemetry: langfuse unreachable at {langfuse['host']} - "
                      "continuing WITHOUT tracing (the loop itself is unaffected)")
                telemetry_down_notice = True
            elif live and telemetry_down_notice:
                print("[driver] telemetry: langfuse back online - tracing re-enabled")
                telemetry_down_notice = False
        telemetry = telemetry_env(langfuse, {
            "service.name": "or-autoresearch",
            "loop.problem": problem,
            "loop.workspace": ws.name,
            "loop.iteration": str(done + 1),
        }) if live else {}
        env = session_env(ws, env_config, telemetry)
        # Post-mortem artifact: the prompt itself is delivered via stdin, but
        # the file records exactly what the session was told.
        (ws / ".driver_prompt.txt").write_text(prompt)
        print(f"[driver] invoking claude for iteration {done + 1}/{iterations}")
        if live:
            print(f"[driver] telemetry: langfuse at {langfuse['host']} (loop.* attributes)")
        rc, timed_out, wall_s = run_claude(ws, cmd, prompt, claude_cap_minutes, env)
        if rc != 0:
            print(f"[driver] claude exited with {rc}")

        try:
            actions = bookkeeping.process(ws, problem)
            for action in actions:
                print(f"[driver] bookkeeping: {action}")
        except Exception as exc:  # bookkeeping must never kill the loop
            print(f"[driver] bookkeeping failed: {exc}")

        rows = count_full(problem_dir)
        _log_invocation(
            ws,
            returncode=rc,
            timeout=timed_out,
            cap_minutes=claude_cap_minutes,
            max_turns=max_turns,
            full_rows_before=prev_rows,
            full_rows_after=rows,
            wall_s=round(wall_s, 1),
            pivot_state=pivot,
            model=env_config.get("ANTHROPIC_MODEL", ""),
            langfuse=bool(live),
        )
        if rows > prev_rows:
            stalled = 0
            new_full = tsv.full_rows(tsv.read(problem_dir))[prev_rows:rows]
            if new_full:
                print("[driver] results this invocation:")
                print(summarize_rows(new_full))
            prev_rows = rows
        else:
            stalled += 1
            if stalled >= 3:
                print("[driver] aborting: 3 consecutive invocations produced no full eval")
                return

    full = tsv.full_rows(tsv.read(problem_dir))
    run_rows = full[start_rows:]
    if run_rows:
        print(f"[driver] results this run ({len(run_rows)} full-subset evals):")
        print(summarize_rows(run_rows))
        best = tsv.best_row(run_rows)
        if best:
            print(f"[driver] best this run: {best.get('candidate_file', '?')} score {best.get('score', '?')}")
    done = prev_rows - start_rows
    if done >= iterations:
        print(f"[driver] done: {done} full iterations this run ({prev_rows} total in history)")
    else:
        print(f"[driver] timeout reached with {done}/{iterations} iterations this run")


def _resolve(cli_value, cfg: dict, key: str, default):
    """CLI flag > loop.json key > module default (same precedence as --iterations)."""
    if cli_value is not None:
        return cli_value
    return cfg.get(key, default)


def current_branch(root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def working_tree_dirty(root: Path) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    return bool(proc.stdout.strip())


def ensure_loop_branch(root: Path, problem: str) -> str:
    """In-place mode never auto-commits onto main/master - make a loop branch."""
    branch = current_branch(root)
    if branch in ("main", "master"):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        new_branch = f"loop/{problem}__{ts}"
        subprocess.run(["git", "-C", str(root), "checkout", "-q", "-b", new_branch], check=True)
        return new_branch
    return branch or "HEAD"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=None, help="overrides loop.json")
    parser.add_argument("--timeout-hours", type=float, default=None,
                        help="overall run timeout; default loop.json / 12h")
    parser.add_argument("--max-turns", type=int, default=None,
                        help="per-invocation claude turn cap; default loop.json / 60")
    parser.add_argument("--claude-cap-minutes", type=float, default=None,
                        help="hard wall-clock cap per claude invocation "
                             "(process-group kill); default loop.json / 20")
    parser.add_argument("--isolate", action="store_true",
                        help="run in a full-copy workspace under loop_runs/ (parallel-safe, "
                             "throwaway); default: IN-PLACE on this repo - the loop commits "
                             "to a loop/<problem>__<ts> branch when started from main/master")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, no changes")
    parser.add_argument("--assemble-only", action="store_true",
                        help="(isolate mode) assemble + git init, no run")
    parser.add_argument("--workspace", default=None,
                        help="resume this existing isolate-mode workspace (skips assembly)")
    args = parser.parse_args()

    cfg = load_config(REPO_ROOT)
    problem = cfg.get("problem", "mdkp")
    iterations = int(_resolve(args.iterations, cfg, "iterations", 15))
    timeout_hours = _resolve(args.timeout_hours, cfg, "timeout_hours", DEFAULT_TIMEOUT_HOURS)
    max_turns = int(_resolve(args.max_turns, cfg, "max_turns", DEFAULT_MAX_TURNS))
    claude_cap_minutes = float(
        _resolve(args.claude_cap_minutes, cfg, "claude_cap_minutes", DEFAULT_CLAUDE_CAP_MINUTES)
    )
    isolate = args.isolate or args.assemble_only or bool(args.workspace)

    if args.dry_run and not isolate:
        branch = current_branch(REPO_ROOT)
        planned = f"loop/{problem}__<ts>" if branch in ("main", "master") else branch
        print(f"[run_loop] dry run: IN-PLACE on {REPO_ROOT}")
        print(f"[run_loop] bookkeeping will commit to branch: {planned}")
        print(f"[run_loop] problem={problem} iterations={iterations} "
              f"cap={claude_cap_minutes}min turns={max_turns} timeout={timeout_hours}h")
        print(f"[run_loop] dirty tree: {'YES (refusing at start)' if working_tree_dirty(REPO_ROOT) else 'clean'}")
        return 0

    if not isolate:
        if working_tree_dirty(REPO_ROOT):
            print("error: working tree has uncommitted changes - commit or stash first "
                  "(the loop commits bookkeeping in-place)")
            return 2
        branch = ensure_loop_branch(REPO_ROOT, problem)
        print(f"[run_loop] mode: IN-PLACE on {REPO_ROOT} (bookkeeping commits to '{branch}')")
        run_driver(REPO_ROOT, problem, iterations, timeout_hours, max_turns, claude_cap_minutes)
        return 0

    if args.workspace:
        ws = Path(args.workspace).resolve()
        if not ws.is_dir():
            print(f"error: workspace {ws} does not exist")
            return 2
        print(f"[run_loop] resuming workspace {ws}")
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ws = REPO_ROOT / "loop_runs" / f"{problem}__{ts}"
        if ws.exists():
            print(f"error: workspace {ws} already exists")
            return 2
        print(f"[run_loop] assembling workspace {ws}")
        assemble_workspace(ws)

    for required in [REPO_ROOT / ".env", ws / "AGENTS.md",
                     ws / "problems" / problem / "reference.json"]:
        if not required.exists():
            print(f"error: missing {required}")
            return 2

    if args.dry_run:
        print(f"[run_loop] dry run - workspace at {ws}")
        for path in sorted(ws.rglob("*")):
            if ".git" in path.parts or ".venv" in path.parts or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ws)
            depth = len(rel.parts) - 1
            if depth > 2:
                continue
            print(f"{'  ' * depth}{'d ' if path.is_dir() else '  '}{rel.parts[-1]}")
        return 0

    if not args.workspace:
        print("[run_loop] initializing git")
        init_git(ws)

    if args.assemble_only:
        print(f"[run_loop] assembled (no run): {ws}")
        return 0

    run_driver(ws, problem, iterations, timeout_hours, max_turns, claude_cap_minutes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
