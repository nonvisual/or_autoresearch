"""Driver pure functions: command, prompt (incl. pivot line), env, sync, telemetry."""

import base64

import scripts.run_loop as drv


def test_claude_command_shape():
    cmd = drv.claude_command(42)
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert cmd[cmd.index("--max-turns") + 1] == "42"
    assert "--output-format" in cmd


def test_summarize_rows_rendes_results():
    rows = [
        {"iteration": "4", "candidate_file": "candidate_dd_beam.py", "score": "0.997137",
         "coverage": "1.0000", "status": "discarded", "hypothesis": "width-limited MDD beam"},
        {"iteration": "12", "candidate_file": "candidate_totalorder_widebeam.py",
         "score": "0.999650", "coverage": "1.0000", "status": "kept",
         "hypothesis": "make the prune a total order"},
    ]
    text = drv.summarize_rows(rows)
    assert "#  4" in text and "candidate_dd_beam.py" in text and "0.997137" in text
    assert "kept" in text and "candidate_totalorder_widebeam.py" in text


def test_iteration_prompt_text():
    text = drv.build_iteration_prompt("DIGEST", 3, 15)
    assert "Iteration 3/15" in text
    assert "DIGEST" in text
    assert "TRUST IT" in text
    assert "ONE full iteration" in text
    assert "Bookkeeping is AUTOMATIC" in text
    assert "CONSTRAINT:" not in text  # no pivot line unless forced


def test_iteration_prompt_pivot_line_only_when_forced():
    text = drv.build_iteration_prompt("DIGEST", 3, 15, must_pivot=True)
    assert "CONSTRAINT:" in text
    assert "DIFFERENT idea" in text


def test_load_env_config_filters(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "ANTHROPIC_API_KEY=secret\n"
        'ANTHROPIC_MODEL="model-x"\n'
        "OTHER=nope\n"
        "MALFORMED\n"
    )
    cfg = drv.load_env_config(env)
    assert cfg == {"ANTHROPIC_API_KEY": "secret", "ANTHROPIC_MODEL": "model-x"}


def test_session_env_isolation(tmp_path):
    env = drv.session_env(tmp_path, {"ANTHROPIC_MODEL": "m"})
    assert env["ANTHROPIC_MODEL"] == "m"
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / ".claude-config")
    assert (tmp_path / ".claude-config").exists()


def test_load_env_config_includes_langfuse_and_otel(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "LANGFUSE_PUBLIC_KEY=pk\n"
        "LANGFUSE_SECRET_KEY=sk\n"
        "OTEL_EXPORTER_OTLP_ENDPOINT=x\n"
        "UNRELATED=1\n"
    )
    cfg = drv.load_env_config(env)
    assert cfg["LANGFUSE_PUBLIC_KEY"] == "pk"
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in cfg
    assert "UNRELATED" not in cfg


def test_langfuse_config_requires_both_keys():
    assert drv.langfuse_config({}) is None
    assert drv.langfuse_config({"LANGFUSE_PUBLIC_KEY": "pk"}) is None
    lf = drv.langfuse_config({"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"})
    assert lf == {"public_key": "pk", "secret_key": "sk", "host": "https://cloud.langfuse.com"}
    self_hosted = drv.langfuse_config(
        {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk",
         "LANGFUSE_HOST": "http://localhost:3000/"}
    )
    assert self_hosted["host"] == "http://localhost:3000"  # trailing slash stripped


def test_telemetry_env_disabled_without_langfuse():
    assert drv.telemetry_env(None, {"a": "b"}) == {}


def test_langfuse_unreachable_returns_false_not_an_error():
    lf = {"public_key": "pk", "secret_key": "sk", "host": "http://127.0.0.1:1"}  # closed port
    assert drv.langfuse_reachable(lf, timeout_s=0.5) is False


def test_telemetry_env_shapes_otel_vars():
    lf = {"public_key": "pk", "secret_key": "sk", "host": "http://localhost:3000"}
    env = drv.telemetry_env(lf, {"loop.iteration": "2", "service.name": "or-autoresearch"})
    token = base64.b64encode(b"pk:sk").decode()
    assert env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    # without the beta flag Claude Code emits no OTLP traces at all; the
    # detailed tier puts content (prompts/tool I/O) on the spans
    assert env["CLAUDE_CODE_ENHANCED_TELEMETRY_BETA"] == "1"
    assert env["ENABLE_BETA_TRACING_DETAILED"] == "1"
    assert env["BETA_TRACING_ENDPOINT"] == "http://localhost:3000/api/public/otel"
    assert env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:3000/api/public/otel"
    assert env["OTEL_EXPORTER_OTLP_HEADERS"] == f"Authorization=Basic {token}"
    assert env["OTEL_TRACES_EXPORTER"] == "otlp"
    assert env["OTEL_METRICS_EXPORTER"] == "none"   # Langfuse ingests traces only
    assert env["OTEL_LOGS_EXPORTER"] == "none"
    assert env["OTEL_TRACES_EXPORT_INTERVAL"] == "1000"
    assert env["OTEL_LOG_USER_PROMPTS"] == "1"
    assert env["OTEL_LOG_TOOL_CONTENT"] == "1"
    assert env["OTEL_RESOURCE_ATTRIBUTES"] == "loop.iteration=2,service.name=or-autoresearch"


def test_session_env_applies_telemetry(tmp_path):
    env = drv.session_env(tmp_path, {}, {"CLAUDE_CODE_ENABLE_TELEMETRY": "1"})
    assert env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    assert "CLAUDE_CONFIG_DIR" in env


def test_resolve_precedence():
    cfg = {"iterations": 5, "max_turns": 7}
    assert drv._resolve(None, cfg, "iterations", 15) == 5   # loop.json beats default
    assert drv._resolve(9, cfg, "iterations", 15) == 9      # CLI beats loop.json
    assert drv._resolve(None, cfg, "timeout_hours", 12.0) == 12.0  # default


def test_hyper_of_filters_keys():
    cfg = {"idea_pivot_n": 3, "iterations": 15, "new_idea_every_n": 5}
    assert drv.hyper_of(cfg) == {"idea_pivot_n": 3, "new_idea_every_n": 5}


def test_sync_user_directions_one_way(tmp_path):
    host = tmp_path / "host" / "problems" / "mdkp"
    ws = tmp_path / "ws" / "problems" / "mdkp"
    host.mkdir(parents=True)
    ws.mkdir(parents=True)
    assert not drv.sync_user_directions(host, ws)  # nothing to sync yet

    src = host / "research" / "ResearchDirectionsUser.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("## U1: idea\n")
    assert drv.sync_user_directions(host, ws)
    dst = ws / "research" / "ResearchDirectionsUser.md"
    assert dst.read_text() == "## U1: idea\n"

    # host edits flow in; ws edits never flow back
    src.write_text("## U1: idea v2\n")
    (ws / "research" / "ResearchDirectionsLLM.md").write_text("## L1: agent idea\n")
    drv.sync_user_directions(host, ws)
    assert dst.read_text() == "## U1: idea v2\n"
    assert not (host / "research" / "ResearchDirectionsLLM.md").exists()


def test_sync_user_directions_same_dir_is_noop(tmp_path):
    pd = tmp_path / "problems" / "mdkp"
    (pd / "research").mkdir(parents=True)
    (pd / "research" / "ResearchDirectionsUser.md").write_text("## U1: idea\n")
    assert drv.sync_user_directions(pd, pd) is False  # in-place mode


def test_ensure_loop_branch_avoids_main(tmp_path, make_git_repo):
    ws = make_git_repo(tmp_path / "repo")
    branch = drv.ensure_loop_branch(ws, "mdkp")
    assert branch.startswith("loop/mdkp__")  # auto-created off main
    assert drv.current_branch(ws) == branch

    branch2 = drv.ensure_loop_branch(ws, "mdkp")
    assert branch2 == branch  # already on a loop branch: reused, not stacked


def test_working_tree_dirty(tmp_path, make_git_repo):
    ws = make_git_repo(tmp_path / "repo")
    assert not drv.working_tree_dirty(ws)
    (ws / "f.txt").write_text("x")
    assert drv.working_tree_dirty(ws)


def test_format_event_renders_tool_use_and_result():
    line = '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"uv run pytest"}}]}}'
    assert drv.format_event(line) == "[claude] Bash(uv run pytest)"
    line = '{"type":"result","subtype":"success","num_turns":4,"duration_ms":1500}'
    assert "session finished: success, 4 turns, 2s" in drv.format_event(line)
    assert drv.format_event("not json") is None
    assert drv.format_event('{"type":"system"}') is None
