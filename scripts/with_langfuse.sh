#!/bin/sh
# Launch a command (typically `claude`) with Claude Code session tracing to
# Langfuse. Reads LANGFUSE_* keys from the repo-root .env.
#
#   scripts/with_langfuse.sh claude        # then /or-iterate inside
#   scripts/with_langfuse.sh claude -p "..." --max-turns 40
#
# Without LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY in .env this exits 2.
# The autonomous driver (scripts/run_loop.py) enables the same telemetry
# automatically when the keys are present - this wrapper is for interactive
# sessions, whose env must be set before claude starts.
#
# CLAUDE_CODE_ENHANCED_TELEMETRY_BETA is the critical flag: without it Claude
# Code exports only log records (no traces), and self-hosted Langfuse v4 has
# no /v1/logs route, so nothing would be ingested. The DETAILED tier adds the
# actual content to spans (user_prompt / response.model_output / tool_input)
# and redirects trace export to BETA_TRACING_ENDPOINT (http/json).
set -eu
cd "$(dirname "$0")/.."

PK=""
SK=""
HOST="${LANGFUSE_HOST:-https://cloud.langfuse.com}"
if [ -f .env ]; then
    while IFS='=' read -r key value; do
        case "$key" in
            LANGFUSE_PUBLIC_KEY) PK=$(printf '%s' "$value" | tr -d "\"' ") ;;
            LANGFUSE_SECRET_KEY) SK=$(printf '%s' "$value" | tr -d "\"' ") ;;
            LANGFUSE_HOST) HOST=$(printf '%s' "$value" | tr -d "\"' ") ;;
        esac
    done < .env
fi
if [ -z "$PK" ] || [ -z "$SK" ]; then
    echo "error: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set in .env" >&2
    exit 2
fi
TOKEN=$(printf '%s:%s' "$PK" "$SK" | base64 | tr -d '\n')

exec env \
    CLAUDE_CODE_ENABLE_TELEMETRY=1 \
    CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1 \
    ENABLE_BETA_TRACING_DETAILED=1 \
    BETA_TRACING_ENDPOINT="${HOST%/}/api/public/otel" \
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
    OTEL_EXPORTER_OTLP_ENDPOINT="${HOST%/}/api/public/otel" \
    OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${TOKEN}" \
    OTEL_TRACES_EXPORTER=otlp \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_TRACES_EXPORT_INTERVAL=1000 \
    OTEL_LOG_USER_PROMPTS=1 \
    OTEL_LOG_TOOL_DETAILS=1 \
    OTEL_LOG_TOOL_CONTENT=1 \
    OTEL_RESOURCE_ATTRIBUTES="service.name=or-autoresearch,loop.mode=interactive" \
    "$@"
