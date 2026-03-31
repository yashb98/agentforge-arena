#!/usr/bin/env bash
# .claude/hooks/post-tool-use/cost-tracker.sh
# Tracks LLM token usage and cost per tournament/team/agent

set -euo pipefail

TOOL_INPUT=$(cat)
AGENT_ID="${AGENT_ID:-unknown}"
TEAM_ID="${TEAM_ID:-unknown}"
TOURNAMENT_ID="${TOURNAMENT_ID:-unknown}"

# Extract token counts from tool result metadata if available
INPUT_TOKENS=$(echo "$TOOL_INPUT" | jq -r '.metadata.input_tokens // 0')
OUTPUT_TOKENS=$(echo "$TOOL_INPUT" | jq -r '.metadata.output_tokens // 0')
MODEL=$(echo "$TOOL_INPUT" | jq -r '.metadata.model // "unknown"')

# Cost per 1M tokens (approximate, update as pricing changes)
declare -A COST_INPUT_PER_M=(
    ["claude-opus-4-6"]="15.00"
    ["claude-sonnet-4-6"]="3.00"
    ["claude-haiku-4-5"]="0.80"
    ["gpt-5"]="10.00"
    ["unknown"]="5.00"
)
declare -A COST_OUTPUT_PER_M=(
    ["claude-opus-4-6"]="75.00"
    ["claude-sonnet-4-6"]="15.00"
    ["claude-haiku-4-5"]="4.00"
    ["gpt-5"]="30.00"
    ["unknown"]="15.00"
)

INPUT_RATE="${COST_INPUT_PER_M[$MODEL]:-5.00}"
OUTPUT_RATE="${COST_OUTPUT_PER_M[$MODEL]:-15.00}"

# Calculate cost
COST=$(python3 -c "
i_tokens = $INPUT_TOKENS
o_tokens = $OUTPUT_TOKENS
i_rate = $INPUT_RATE
o_rate = $OUTPUT_RATE
cost = (i_tokens * i_rate / 1_000_000) + (o_tokens * o_rate / 1_000_000)
print(f'{cost:.6f}')
" 2>/dev/null || echo "0.000000")

# Append to cost ledger
COST_FILE="/var/log/agentforge/costs/${TOURNAMENT_ID}.jsonl"
mkdir -p "$(dirname "$COST_FILE")"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "{\"timestamp\":\"$TIMESTAMP\",\"tournament\":\"$TOURNAMENT_ID\",\"team\":\"$TEAM_ID\",\"agent\":\"$AGENT_ID\",\"model\":\"$MODEL\",\"input_tokens\":$INPUT_TOKENS,\"output_tokens\":$OUTPUT_TOKENS,\"cost_usd\":$COST}" >> "$COST_FILE"

# Check budget threshold via Redis
REDIS_HOST="${REDIS_HOST:-localhost}"
if command -v redis-cli &> /dev/null; then
    redis-cli -h "$REDIS_HOST" INCRBYFLOAT "cost:${TOURNAMENT_ID}:total" "$COST" 2>/dev/null || true
    redis-cli -h "$REDIS_HOST" INCRBYFLOAT "cost:${TOURNAMENT_ID}:${TEAM_ID}" "$COST" 2>/dev/null || true
fi

exit 0
