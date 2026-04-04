"""Static files seeded into each team's sandbox ``project/`` root."""

from __future__ import annotations

from pathlib import Path

# Optional `.claude/settings.json` for Anthropic Claude Code — other runtimes (Codex, Gemini CLI,
# OpenCode, …) should seed their own config via ``agent_runtime``-specific bootstrap when added.
# Broad allow inside the sandbox project only (MicroVM is the trust boundary).
# ``defaultMode: bypassPermissions`` matches Claude Code permission modes (no interactive asks in
# this project). See https://code.claude.com/docs/en/settings — org ``managed`` policies can still
# override. ``skipDangerousModePermissionPrompt`` is ignored in project scope per upstream docs.
# Omit hooks here — team projects start without monorepo hook scripts.
TEAM_PROJECT_CLAUDE_SETTINGS_JSON = """{
  "permissions": {
    "defaultMode": "bypassPermissions",
    "allow": [
      "Read",
      "Write(**)",
      "Edit(**)",
      "Bash(*)"
    ],
    "deny": [
      "Write(.env)",
      "Write(*.pem)",
      "Write(*.key)",
      "Edit(.env)",
      "Edit(*.pem)",
      "Edit(*.key)"
    ]
  }
}
"""

TEAM_PROJECT_RULE_RESEARCH_FIRST = """---
description: Verify and refresh knowledge before non-trivial implementation
---

# Research before implementation

Before **new** implementation work (new modules, APIs, dependencies, or behavior):

1. **Re-read** `CHALLENGE.md`, `challenge.spec.json`, and your team's `RESEARCH.md` / architecture docs.
2. **Check current facts** — library APIs, breaking changes, and defaults change; prefer targeted search or docs over stale training recall.
3. **Update artifacts** — if research changes the plan, revise `RESEARCH.md`, `ARCHITECTURE.md`, or ADRs in `docs/decisions/` before or alongside code.
4. **Small fixes** (typos, obvious bugs with local proof) do not require a full research cycle.

This rule applies only inside this team project, not the AgentForge Arena monorepo.
"""

# MCP config for [code-review-graph](https://github.com/tirth8205/code-review-graph) (stdio server).
# In restricted sandboxes without network/`uvx`, install `code-review-graph` into the project venv and
# point ``command`` at that binary, or disable this server in ``.mcp.json``.
TEAM_PROJECT_MCP_JSON = """{
  "mcpServers": {
    "code-review-graph": {
      "command": "uvx",
      "args": ["code-review-graph", "serve"],
      "type": "stdio"
    }
  }
}
"""

TEAM_PROJECT_CODE_REVIEW_GRAPHIGNORE = """# code-review-graph — paths to skip in this team project
.venv/
venv/
env/
node_modules/
__pycache__/
*.egg-info/
dist/
build/
.next/
out/
.coverage
htmlcov/
.git/
"""


def write_team_code_review_graph_seed(project_root: Path) -> None:
    """Write ``.mcp.json`` and ``.code-review-graphignore`` for code-review-graph (project root)."""
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".mcp.json").write_text(
        TEAM_PROJECT_MCP_JSON.strip() + "\n",
        encoding="utf-8",
    )
    (project_root / ".code-review-graphignore").write_text(
        TEAM_PROJECT_CODE_REVIEW_GRAPHIGNORE.strip() + "\n",
        encoding="utf-8",
    )
