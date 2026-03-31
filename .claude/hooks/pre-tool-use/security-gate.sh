#!/usr/bin/env bash
# .claude/hooks/pre-tool-use/security-gate.sh
# AgentShield-inspired security scanner
# Runs BEFORE any Bash or Write tool use inside agent sandboxes
#
# Exit 0 = allow, Exit 1 = block
# Reads tool input from stdin as JSON: { "tool": "bash", "input": "..." }

set -euo pipefail

TOOL_INPUT=$(cat)
TOOL_NAME=$(echo "$TOOL_INPUT" | jq -r '.tool // "unknown"')
TOOL_COMMAND=$(echo "$TOOL_INPUT" | jq -r '.input // ""')
TOOL_FILE=$(echo "$TOOL_INPUT" | jq -r '.file // ""')
AGENT_ID="${AGENT_ID:-unknown}"
TEAM_ID="${TEAM_ID:-unknown}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

LOG_FILE="/var/log/agentforge/security-gate.jsonl"
mkdir -p "$(dirname "$LOG_FILE")"

log_event() {
    local severity="$1"
    local rule="$2"
    local detail="$3"
    echo "{\"timestamp\":\"$TIMESTAMP\",\"agent\":\"$AGENT_ID\",\"team\":\"$TEAM_ID\",\"tool\":\"$TOOL_NAME\",\"severity\":\"$severity\",\"rule\":\"$rule\",\"detail\":\"$detail\"}" >> "$LOG_FILE"
}

block() {
    local rule="$1"
    local detail="$2"
    log_event "CRITICAL" "$rule" "$detail"
    echo "BLOCKED by AgentShield: $rule — $detail" >&2
    exit 1
}

warn() {
    local rule="$1"
    local detail="$2"
    log_event "WARNING" "$rule" "$detail"
}

# ============================================================
# RULE SET: Bash Command Scanning
# ============================================================
if [ "$TOOL_NAME" = "bash" ]; then

    # --- Container Escape Prevention ---
    if echo "$TOOL_COMMAND" | grep -qiE '(nsenter|unshare|chroot|pivot_root|mount.*proc)'; then
        block "CONTAINER_ESCAPE" "Attempted container escape: $TOOL_COMMAND"
    fi

    # --- Privilege Escalation ---
    if echo "$TOOL_COMMAND" | grep -qiE '^sudo|chmod\s+777|chown\s+root|setuid'; then
        block "PRIVILEGE_ESCALATION" "Privilege escalation attempt: $TOOL_COMMAND"
    fi

    # --- Destructive Operations ---
    if echo "$TOOL_COMMAND" | grep -qiE 'rm\s+-rf\s+/[^a]|mkfs|dd\s+if.*of=/dev'; then
        block "DESTRUCTIVE_OP" "Destructive filesystem operation: $TOOL_COMMAND"
    fi

    # --- Network Exfiltration ---
    if echo "$TOOL_COMMAND" | grep -qiE 'curl|wget|nc\s|netcat|ncat'; then
        ALLOWED_DOMAINS="pypi.org|registry.npmjs.org|api.github.com|github.com|api.anthropic.com|api.openai.com|arxiv.org"
        if ! echo "$TOOL_COMMAND" | grep -qiE "($ALLOWED_DOMAINS)"; then
            # Check if it's a non-network curl (file://, etc.)
            if echo "$TOOL_COMMAND" | grep -qiE 'https?://'; then
                block "NETWORK_EXFIL" "Network request to non-whitelisted domain: $TOOL_COMMAND"
            fi
        fi
    fi

    # --- Reverse Shell Detection ---
    if echo "$TOOL_COMMAND" | grep -qiE 'bash\s+-i|/dev/tcp|mkfifo.*nc|python.*socket.*connect'; then
        block "REVERSE_SHELL" "Reverse shell attempt detected: $TOOL_COMMAND"
    fi

    # --- Crypto Mining ---
    if echo "$TOOL_COMMAND" | grep -qiE 'xmrig|minerd|cgminer|stratum\+tcp'; then
        block "CRYPTO_MINING" "Cryptocurrency mining attempt: $TOOL_COMMAND"
    fi

    # --- Docker Escape ---
    if echo "$TOOL_COMMAND" | grep -qiE 'docker\s+run|docker\s+exec|docker\s+cp|dockerd'; then
        block "DOCKER_ESCAPE" "Docker command inside sandbox: $TOOL_COMMAND"
    fi

    # --- Process Manipulation ---
    if echo "$TOOL_COMMAND" | grep -qiE 'kill\s+-9\s+1|killall|pkill.*init'; then
        block "PROCESS_MANIPULATION" "Attempted to kill system processes: $TOOL_COMMAND"
    fi

    # --- Environment Variable Extraction ---
    if echo "$TOOL_COMMAND" | grep -qiE 'printenv|env\s*$|cat.*/proc/.*/environ|echo.*\$[A-Z_]*(KEY|SECRET|TOKEN|PASSWORD)'; then
        block "SECRET_EXTRACTION" "Attempted to extract secrets: $TOOL_COMMAND"
    fi

    # --- Pipe to Execution ---
    if echo "$TOOL_COMMAND" | grep -qiE 'curl.*\|\s*(bash|sh|python|node|perl)|wget.*\|\s*(bash|sh)'; then
        block "PIPE_EXEC" "Remote code execution via pipe: $TOOL_COMMAND"
    fi

fi

# ============================================================
# RULE SET: File Write Scanning
# ============================================================
if [ "$TOOL_NAME" = "write" ] || [ "$TOOL_NAME" = "create_file" ]; then

    # --- Secrets in Code ---
    CONTENT=$(echo "$TOOL_INPUT" | jq -r '.content // ""')

    # AWS Keys
    if echo "$CONTENT" | grep -qE 'AKIA[0-9A-Z]{16}'; then
        block "SECRET_IN_CODE" "AWS Access Key detected in file write"
    fi

    # Generic API Keys / Tokens
    if echo "$CONTENT" | grep -qiE '(api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token)\s*[=:]\s*["\x27][a-zA-Z0-9+/=_-]{20,}'; then
        warn "POSSIBLE_SECRET" "Possible API key/token in file content"
    fi

    # Private Keys
    if echo "$CONTENT" | grep -qE '-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----'; then
        block "PRIVATE_KEY" "Private key detected in file write"
    fi

    # --- Path Traversal ---
    if echo "$TOOL_FILE" | grep -qE '\.\./' ; then
        block "PATH_TRAVERSAL" "Path traversal attempt: $TOOL_FILE"
    fi

    # --- Writing Outside Workspace ---
    WORKSPACE="/arena/team-${TEAM_ID}"
    if [ -n "$TOOL_FILE" ] && [[ ! "$TOOL_FILE" == ${WORKSPACE}/* ]] && [[ ! "$TOOL_FILE" == .//* ]]; then
        block "WORKSPACE_ESCAPE" "Write outside workspace: $TOOL_FILE (expected: $WORKSPACE/*)"
    fi

fi

# All checks passed
log_event "INFO" "ALLOWED" "Tool use permitted: $TOOL_NAME"
exit 0
