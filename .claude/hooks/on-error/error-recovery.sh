#!/usr/bin/env bash
# .claude/hooks/on-error/error-recovery.sh
# Error-tolerant rollout — let agents recover from mistakes instead of terminating
# Based on "From Spark to Fire" error cascade mitigation research

set -euo pipefail

ERROR_INPUT=$(cat)
ERROR_TYPE=$(echo "$ERROR_INPUT" | jq -r '.error_type // "unknown"')
ERROR_MSG=$(echo "$ERROR_INPUT" | jq -r '.error_message // ""')
TOOL_NAME=$(echo "$ERROR_INPUT" | jq -r '.tool // "unknown"')
AGENT_ID="${AGENT_ID:-unknown}"
TEAM_ID="${TEAM_ID:-unknown}"
TOURNAMENT_ID="${TOURNAMENT_ID:-unknown}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

LOG_FILE="/var/log/agentforge/errors/${TOURNAMENT_ID}.jsonl"
mkdir -p "$(dirname "$LOG_FILE")"

log_error() {
    echo "{\"timestamp\":\"$TIMESTAMP\",\"agent\":\"$AGENT_ID\",\"team\":\"$TEAM_ID\",\"tool\":\"$TOOL_NAME\",\"error_type\":\"$ERROR_TYPE\",\"error_message\":\"$ERROR_MSG\",\"recovery\":\"$1\"}" >> "$LOG_FILE"
}

# Track consecutive failures per agent
FAIL_KEY="errors:${TOURNAMENT_ID}:${TEAM_ID}:${AGENT_ID}:consecutive"
REDIS_HOST="${REDIS_HOST:-localhost}"
FAIL_COUNT=0

if command -v redis-cli &> /dev/null; then
    FAIL_COUNT=$(redis-cli -h "$REDIS_HOST" INCR "$FAIL_KEY" 2>/dev/null || echo "1")
    redis-cli -h "$REDIS_HOST" EXPIRE "$FAIL_KEY" 300 2>/dev/null || true
fi

# ============================================================
# Recovery Strategies Based on Error Type
# ============================================================

case "$ERROR_TYPE" in
    "timeout")
        log_error "RETRY_WITH_BACKOFF"
        # Exponential backoff: 2^fail_count seconds, max 60s
        BACKOFF=$((2 ** FAIL_COUNT > 60 ? 60 : 2 ** FAIL_COUNT))
        echo "{\"action\":\"retry\",\"delay_seconds\":$BACKOFF,\"message\":\"Timeout - retrying in ${BACKOFF}s\"}"
        ;;

    "rate_limit")
        log_error "RATE_LIMIT_BACKOFF"
        echo "{\"action\":\"retry\",\"delay_seconds\":30,\"message\":\"Rate limited - waiting 30s\"}"
        ;;

    "syntax_error"|"compilation_error")
        log_error "SELF_FIX"
        echo "{\"action\":\"self_fix\",\"message\":\"Syntax error detected - agent should review and fix\"}"
        # Reset consecutive failures for self-fixable errors
        redis-cli -h "$REDIS_HOST" SET "$FAIL_KEY" 0 2>/dev/null || true
        ;;

    "test_failure")
        log_error "CONTINUE"
        echo "{\"action\":\"continue\",\"message\":\"Test failure - agent should fix failing tests\"}"
        redis-cli -h "$REDIS_HOST" SET "$FAIL_KEY" 0 2>/dev/null || true
        ;;

    "dependency_error")
        log_error "RETRY_WITH_FALLBACK"
        echo "{\"action\":\"retry\",\"message\":\"Dependency error - try alternative package or pin version\"}"
        ;;

    "out_of_memory")
        log_error "ESCALATE"
        echo "{\"action\":\"escalate\",\"target\":\"orchestrator\",\"message\":\"OOM in sandbox - need resource increase or optimization\"}"
        ;;

    *)
        if [ "$FAIL_COUNT" -ge 5 ]; then
            log_error "ESCALATE_TO_ARCHITECT"
            echo "{\"action\":\"escalate\",\"target\":\"architect\",\"message\":\"$AGENT_ID has failed $FAIL_COUNT times consecutively - needs intervention\"}"
            # Notify via Redis pub/sub
            if command -v redis-cli &> /dev/null; then
                redis-cli -h "$REDIS_HOST" PUBLISH "tournament:${TOURNAMENT_ID}:events" \
                    "{\"type\":\"agent.error.escalated\",\"agent\":\"$AGENT_ID\",\"team\":\"$TEAM_ID\",\"failures\":$FAIL_COUNT}" 2>/dev/null || true
            fi
        elif [ "$FAIL_COUNT" -ge 3 ]; then
            log_error "SIMPLIFY"
            echo "{\"action\":\"simplify\",\"message\":\"Multiple failures - agent should simplify approach\"}"
        else
            log_error "RETRY"
            echo "{\"action\":\"retry\",\"delay_seconds\":5,\"message\":\"Retrying after error\"}"
        fi
        ;;
esac

exit 0
