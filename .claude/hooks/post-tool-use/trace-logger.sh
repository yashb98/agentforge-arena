#!/usr/bin/env bash
# .claude/hooks/post-tool-use/trace-logger.sh
# Logs every tool use to Langfuse for full replay capability
# Also publishes to Redis for real-time spectator streaming

set -euo pipefail

TOOL_INPUT=$(cat)
TOOL_NAME=$(echo "$TOOL_INPUT" | jq -r '.tool // "unknown"')
TOOL_RESULT=$(echo "$TOOL_INPUT" | jq -r '.result // "success"')
AGENT_ID="${AGENT_ID:-unknown}"
TEAM_ID="${TEAM_ID:-unknown}"
TOURNAMENT_ID="${TOURNAMENT_ID:-unknown}"
TRACE_ID="${TRACE_ID:-$(uuidgen 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# ---- Langfuse Trace (File-based for reliability) ----
TRACE_DIR="/var/log/agentforge/traces/${TOURNAMENT_ID}"
mkdir -p "$TRACE_DIR"

TRACE_EVENT=$(cat <<EOF
{
  "trace_id": "$TRACE_ID",
  "tournament_id": "$TOURNAMENT_ID",
  "team_id": "$TEAM_ID",
  "agent_id": "$AGENT_ID",
  "tool": "$TOOL_NAME",
  "result": "$TOOL_RESULT",
  "timestamp": "$TIMESTAMP",
  "phase": "${CURRENT_PHASE:-unknown}"
}
EOF
)

echo "$TRACE_EVENT" >> "${TRACE_DIR}/${TEAM_ID}-${AGENT_ID}.jsonl"

# ---- Redis Pub/Sub for Real-Time Spectator ----
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

if command -v redis-cli &> /dev/null; then
    REDIS_EVENT=$(cat <<EOF
{
  "type": "agent.tool.used",
  "tournament_id": "$TOURNAMENT_ID",
  "team_id": "$TEAM_ID",
  "agent_id": "$AGENT_ID",
  "tool": "$TOOL_NAME",
  "timestamp": "$TIMESTAMP"
}
EOF
)
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
        PUBLISH "tournament:${TOURNAMENT_ID}:events" "$REDIS_EVENT" \
        2>/dev/null || true
fi

exit 0
