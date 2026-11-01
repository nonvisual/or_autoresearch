---
name: langfuse
description: Observability for or_autoresearch sessions in Langfuse - launch traced sessions, verify trace ingestion, inspect what the loop logged, and troubleshoot missing traces. Use when the user asks about tracing, telemetry, observability, or "what did the loop log".
---

# langfuse: session observability

Every Claude Code session (autonomous driver iteration or interactive
/or-iterate) can ship detailed traces to Langfuse: one trace per session -
`claude_code.interaction` root with nested `claude_code.llm_request`
(GENERATION: model, tokens, cost, ttft) and `claude_code.tool` spans (TOOL:
Bash, Read, Task/subagents...) including prompts and tool content.

## Launch a traced session

- Interactive: `scripts/with_langfuse.sh claude` (env must precede claude),
  then `/or-iterate` inside as usual. Traces carry `loop.mode=interactive`.
- Autonomous loop: put `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`
  (and `LANGFUSE_HOST` if self-hosted) in `.env`; `scripts/run_loop.py`
  enables telemetry automatically and tags each iteration's traces with
  `service.name=or-autoresearch`, `loop.problem`, `loop.workspace`,
  `loop.iteration` - filter by these in the Langfuse UI.

## The env that must exist BEFORE claude starts

`scripts/with_langfuse.sh` and `telemetry_env()` in `scripts/run_loop.py` are
the sources of truth. Critical facts (do not re-derive):

- `CLAUDE_CODE_ENABLE_TELEMETRY=1` **and** `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`
  are BOTH required - without the beta flag Claude Code exports only log
  records, and self-hosted Langfuse v4 has no `/v1/logs` route, so nothing is
  ingested.
- Exporter: `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`,
  `OTEL_EXPORTER_OTLP_ENDPOINT=<host>/api/public/otel`,
  `OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic base64(pk:sk)`.
  Metrics/logs exporters stay `none` (traces only).
- `OTEL_TRACES_EXPORT_INTERVAL=1000` flushes short sessions;
  `OTEL_LOG_USER_PROMPTS=1` / `OTEL_LOG_TOOL_DETAILS=1` /
  `OTEL_LOG_TOOL_CONTENT=1` un-redact content.
- OTel vars are read once at claude startup and are IGNORED in repo
  `.claude/settings.json` - they must come from the shell/user env (which is
  why the wrapper and driver inject them).
- `OTEL_RESOURCE_ATTRIBUTES` values must not contain spaces.

## Where input/output lives in the UI

The trace tree shows structure by default; the CONTENT sits in each span's
ATTRIBUTES section (expand the span):
- `claude_code.interaction` -> `user_prompt` (the prompt text)
- `claude_code.llm_request` -> `response.model_output` (assistant reply),
  `system_prompt_preview`, `tools`, token counts
- tool spans (`Bash`, `Read`, ...) -> `tool_input` (exact command/args)

These come from the detailed tracing tier (`ENABLE_BETA_TRACING_DETAILED=1` +
`BETA_TRACING_ENDPOINT`); without it spans carry only metadata (model, tokens,
timing). To surface them in the Input/Output panes instead of attributes,
map `attributes.user_prompt` / `attributes.response.model_output` in the
Langfuse project's attribute-mapping settings.

## Verify ingestion

1. Stack up? `docker-compose -f <langfuse compose dir>/docker-compose.yml ps`
   (start with `up -d`; this machine: `~/Repositories/langfuse_local`, UI at
   http://localhost:3300, project `or-autoresearch`).
2. Spans landed? Query ClickHouse directly:
   `... exec -T clickhouse clickhouse-client --query "select toString(start_time), name, type from events_core order by start_time desc limit 10"`
   (UI lags a few seconds behind ingestion).
3. Content attached?
   `select name, arrayFilter(x -> position(x, 'user_prompt') > 0 or position(x, 'model_output') > 0 or position(x, 'tool_input') > 0, metadata_names) from events_full ...`
4. UI: Langfuse project traces, filtered by `loop.problem` / `loop.iteration`.

## Troubleshoot

- **Langfuse not running?** Everything still works - telemetry is strictly
  optional: the driver detects an unreachable host per iteration, prints one
  "continuing WITHOUT tracing" notice, and keeps looping (re-checks each
  iteration, so starting the stack mid-run re-enables tracing);
  `with_langfuse.sh` launches the command plainly instead. Never start the
  stack just to unblock a run.
- **No traces at all** -> cause #1 is the missing beta flag; #2 is launching
  claude without the env (setting it inside the session is too late);
  #3 is dead Langfuse (check stack). `claude --debug-file /tmp/cc-debug.log`
  shows `[3P telemetry]` exporter errors.
- **404 on /v1/logs or /v1/metrics** -> expected on self-hosted v4; keep those
  exporters `none`.
- **Wrong keys** -> basic-auth 401s; recheck pk/sk pair and project.
- Long-running stack: needs a VM with ~4+ GiB RAM (a 2 GiB docker VM
  OOM-crash-loops it).
