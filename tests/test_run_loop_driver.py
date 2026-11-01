"""Driver pure functions: command, prompt (incl. pivot line), env, sync."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import scripts.run_loop as drv


def test_claude_command_shape():
    cmd = drv.claude_command(42)
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert cmd[cmd.index("--max-turns") + 1] == "42"
    assert "--output-format" in cmd


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


def test_format_event_renders_tool_use_and_result():
    line = '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"uv run pytest"}}]}}'
    assert drv.format_event(line) == "[claude] Bash(uv run pytest)"
    line = '{"type":"result","subtype":"success","num_turns":4,"duration_ms":1500}'
    assert "session finished: success, 4 turns, 2s" in drv.format_event(line)
    assert drv.format_event("not json") is None
    assert drv.format_event('{"type":"system"}') is None
