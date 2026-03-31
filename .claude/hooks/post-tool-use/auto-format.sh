#!/usr/bin/env bash
# .claude/hooks/post-tool-use/auto-format.sh
# Runs formatters after file writes to maintain consistent code style
# Triggered after: Write, CreateFile tool use

set -euo pipefail

TOOL_INPUT=$(cat)
TOOL_NAME=$(echo "$TOOL_INPUT" | jq -r '.tool // "unknown"')
FILE_PATH=$(echo "$TOOL_INPUT" | jq -r '.file // .path // ""')

# Only run on file write operations
if [ "$TOOL_NAME" != "write" ] && [ "$TOOL_NAME" != "create_file" ]; then
    exit 0
fi

# Skip if no file path
if [ -z "$FILE_PATH" ] || [ "$FILE_PATH" = "null" ]; then
    exit 0
fi

# Get file extension
EXT="${FILE_PATH##*.}"

case "$EXT" in
    py)
        # Python: ruff format + isort
        if command -v ruff &> /dev/null; then
            ruff format "$FILE_PATH" 2>/dev/null || true
            ruff check --fix --select=I "$FILE_PATH" 2>/dev/null || true
        fi
        ;;
    ts|tsx|js|jsx)
        # TypeScript/JavaScript: prettier
        if command -v npx &> /dev/null; then
            npx prettier --write "$FILE_PATH" 2>/dev/null || true
        fi
        ;;
    json)
        # JSON: python json.tool for formatting
        if command -v python3 &> /dev/null; then
            python3 -m json.tool "$FILE_PATH" > "${FILE_PATH}.tmp" 2>/dev/null && mv "${FILE_PATH}.tmp" "$FILE_PATH" || rm -f "${FILE_PATH}.tmp"
        fi
        ;;
    yaml|yml)
        # YAML: no-op (yamlfmt if available)
        if command -v yamlfmt &> /dev/null; then
            yamlfmt "$FILE_PATH" 2>/dev/null || true
        fi
        ;;
    md)
        # Markdown: no formatting needed
        ;;
    *)
        # Unknown extension: skip
        ;;
esac

exit 0
