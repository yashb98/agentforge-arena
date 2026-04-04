"""LLM HTTP timeout settings (defaults + per-task bases)."""

from __future__ import annotations

from packages.shared.src.config import LLMSettings


def test_llm_settings_default_and_per_task_timeouts() -> None:
    s = LLMSettings()
    assert s.timeout_seconds == 60
    assert s.timeout_agent_tools_seconds == 90
    assert s.timeout_agent_planning_seconds == 180
    assert s.timeout_floor_seconds == 10
    assert s.timeout_ceiling_seconds == 900
