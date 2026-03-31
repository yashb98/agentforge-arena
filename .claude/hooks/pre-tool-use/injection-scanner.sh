#!/usr/bin/env bash
# .claude/hooks/pre-tool-use/injection-scanner.sh
# parry-inspired prompt injection detection
# Scans tool inputs/outputs for prompt injection attempts
#
# Exit 0 = allow, Exit 1 = block

set -euo pipefail

TOOL_INPUT=$(cat)
TOOL_NAME=$(echo "$TOOL_INPUT" | jq -r '.tool // "unknown"')
CONTENT=$(echo "$TOOL_INPUT" | jq -r '.input // .content // ""')
AGENT_ID="${AGENT_ID:-unknown}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

LOG_FILE="/var/log/agentforge/injection-scanner.jsonl"
mkdir -p "$(dirname "$LOG_FILE")"

log_event() {
    echo "{\"timestamp\":\"$TIMESTAMP\",\"agent\":\"$AGENT_ID\",\"tool\":\"$TOOL_NAME\",\"severity\":\"$1\",\"pattern\":\"$2\"}" >> "$LOG_FILE"
}

block() {
    log_event "CRITICAL" "$1"
    echo "BLOCKED by Injection Scanner: $1" >&2
    exit 1
}

# ============================================================
# Prompt Injection Patterns
# ============================================================

# Direct injection attempts
if echo "$CONTENT" | grep -qiE 'ignore (previous|all|above) instructions'; then
    block "DIRECT_INJECTION: ignore previous instructions"
fi

if echo "$CONTENT" | grep -qiE 'you are now|new instructions:|system prompt:|override:'; then
    block "DIRECT_INJECTION: role override attempt"
fi

if echo "$CONTENT" | grep -qiE 'forget (everything|your rules|your instructions)'; then
    block "DIRECT_INJECTION: memory wipe attempt"
fi

# Indirect injection (in fetched content)
if echo "$CONTENT" | grep -qiE '<\s*(system|instructions|prompt)\s*>'; then
    block "INDIRECT_INJECTION: embedded system tags in content"
fi

if echo "$CONTENT" | grep -qiE '\[SYSTEM\]|\[INST\]|\[/INST\]|<<SYS>>|<\|im_start\|>'; then
    block "INDIRECT_INJECTION: model-specific control tokens"
fi

# Data exfiltration via output
if echo "$CONTENT" | grep -qiE 'send (this|all|the) (data|content|code|file) to'; then
    block "DATA_EXFIL: data exfiltration instruction"
fi

if echo "$CONTENT" | grep -qiE 'encode.*base64.*send|exfiltrate|POST.*to.*http'; then
    block "DATA_EXFIL: encoded exfiltration attempt"
fi

# Jailbreak patterns
if echo "$CONTENT" | grep -qiE 'DAN mode|developer mode|unrestricted mode|no limits mode'; then
    block "JAILBREAK: mode switch attempt"
fi

if echo "$CONTENT" | grep -qiE 'pretend (you are|to be|you.re) (a|an|not)'; then
    block "JAILBREAK: identity manipulation"
fi

# All checks passed
log_event "INFO" "CLEAN"
exit 0
