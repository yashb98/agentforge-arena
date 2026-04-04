"""Team project seed files (Claude Code settings, etc.)."""

from __future__ import annotations

import json

from packages.sandbox.src.docker.team_workspace_seed import TEAM_PROJECT_CLAUDE_SETTINGS_JSON


def test_team_claude_settings_is_valid_json_with_bypass_permissions_mode() -> None:
    data = json.loads(TEAM_PROJECT_CLAUDE_SETTINGS_JSON)
    perms = data["permissions"]
    assert perms["defaultMode"] == "bypassPermissions"
    assert "Bash(*)" in perms["allow"]
    assert "Write(.env)" in perms["deny"]
