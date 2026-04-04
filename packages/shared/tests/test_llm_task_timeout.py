"""Per-task LLM HTTP timeout resolution and agent message → task kind mapping."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from packages.shared.src.config import LLMSettings
from packages.shared.src.llm.task_timeout import (
    LLMTaskKind,
    infer_agent_llm_task_kind,
    resolve_llm_timeout_seconds,
)
from packages.shared.src.types.models import AgentMessage, AgentRole, MessageType


def _msg(
    message_type: MessageType,
    *,
    role: AgentRole = AgentRole.BUILDER,
    from_role: AgentRole = AgentRole.ARCHITECT,
) -> AgentMessage:
    return AgentMessage(
        id=uuid4(),
        from_agent=from_role,
        to_agent=role,
        message_type=message_type,
        timestamp=datetime.utcnow(),
        correlation_id=uuid4(),
        payload={},
    )


class TestInferAgentLlmTaskKind:
    def test_review_messages_are_review_kind(self) -> None:
        assert infer_agent_llm_task_kind(
            _msg(MessageType.REVIEW_REQUEST), role=AgentRole.CRITIC
        ) == LLMTaskKind.AGENT_REVIEW
        assert infer_agent_llm_task_kind(
            _msg(MessageType.REVIEW_FEEDBACK), role=AgentRole.BUILDER
        ) == LLMTaskKind.AGENT_REVIEW

    def test_architecture_update_is_planning(self) -> None:
        assert infer_agent_llm_task_kind(
            _msg(MessageType.ARCHITECTURE_UPDATE), role=AgentRole.BUILDER
        ) == LLMTaskKind.AGENT_PLANNING_WRITE

    def test_researcher_role_gets_synthesis_bucket(self) -> None:
        assert infer_agent_llm_task_kind(
            _msg(MessageType.TASK_ASSIGNMENT), role=AgentRole.RESEARCHER
        ) == LLMTaskKind.AGENT_RESEARCH_SYNTHESIS

    def test_builder_task_assignment_is_tool_loop(self) -> None:
        assert infer_agent_llm_task_kind(
            _msg(MessageType.TASK_ASSIGNMENT), role=AgentRole.BUILDER
        ) == LLMTaskKind.AGENT_TOOL_LOOP


class TestResolveLlmTimeoutSeconds:
    def test_planning_base_exceeds_default_kind(self) -> None:
        llm = LLMSettings()
        d = resolve_llm_timeout_seconds(llm, LLMTaskKind.DEFAULT, max_tokens=256)
        p = resolve_llm_timeout_seconds(llm, LLMTaskKind.AGENT_PLANNING_WRITE, max_tokens=256)
        assert p > d

    def test_larger_max_tokens_increases_timeout(self) -> None:
        llm = LLMSettings()
        low = resolve_llm_timeout_seconds(llm, LLMTaskKind.DEFAULT, max_tokens=256)
        high = resolve_llm_timeout_seconds(llm, LLMTaskKind.DEFAULT, max_tokens=16_384)
        assert high >= low

    def test_tool_round_index_adds_bounded_bump(self) -> None:
        llm = LLMSettings()
        r0 = resolve_llm_timeout_seconds(
            llm, LLMTaskKind.AGENT_TOOL_LOOP, max_tokens=1024, tool_round_index=0
        )
        r5 = resolve_llm_timeout_seconds(
            llm, LLMTaskKind.AGENT_TOOL_LOOP, max_tokens=1024, tool_round_index=5
        )
        assert r5 > r0
        r99 = resolve_llm_timeout_seconds(
            llm, LLMTaskKind.AGENT_TOOL_LOOP, max_tokens=1024, tool_round_index=99
        )
        assert r99 == resolve_llm_timeout_seconds(
            llm, LLMTaskKind.AGENT_TOOL_LOOP, max_tokens=1024, tool_round_index=10
        )

    def test_has_tools_raises_floor_for_agent_tasks(self) -> None:
        llm = LLMSettings(timeout_agent_tools_seconds=30, timeout_agent_tools_floor=80)
        no_tools = resolve_llm_timeout_seconds(
            llm, LLMTaskKind.AGENT_TOOL_LOOP, max_tokens=256, has_tools=False
        )
        with_tools = resolve_llm_timeout_seconds(
            llm, LLMTaskKind.AGENT_TOOL_LOOP, max_tokens=256, has_tools=True
        )
        assert with_tools >= 80
        assert no_tools == 30
        assert with_tools > no_tools

    def test_agent_ceiling_caps_resolution(self) -> None:
        llm = LLMSettings()
        uncapped = resolve_llm_timeout_seconds(
            llm, LLMTaskKind.AGENT_PLANNING_WRITE, max_tokens=8192
        )
        capped = resolve_llm_timeout_seconds(
            llm,
            LLMTaskKind.AGENT_PLANNING_WRITE,
            max_tokens=8192,
            agent_timeout_ceiling=60,
        )
        assert capped <= 60
        assert uncapped >= capped

    def test_sub_floor_ceiling_is_raised_to_global_floor(self) -> None:
        llm = LLMSettings(timeout_floor_seconds=15)
        out = resolve_llm_timeout_seconds(
            llm,
            LLMTaskKind.DEFAULT,
            max_tokens=256,
            agent_timeout_ceiling=5,
        )
        assert out >= 15

    def test_global_ceiling_clamps(self) -> None:
        llm = LLMSettings(
            timeout_agent_planning_seconds=800,
            timeout_ceiling_seconds=120,
        )
        out = resolve_llm_timeout_seconds(
            llm, LLMTaskKind.AGENT_PLANNING_WRITE, max_tokens=100_000
        )
        assert out <= 120

    def test_missing_per_kind_attr_falls_back_to_timeout_seconds(self) -> None:
        class Partial:
            timeout_seconds = 55

        p = Partial()
        out = resolve_llm_timeout_seconds(
            p, LLMTaskKind.RESEARCH_PEER_REVIEW, max_tokens=256
        )
        assert out >= 55

    @pytest.mark.parametrize(
        ("kind", "minimum"),
        [
            (LLMTaskKind.MEMORY_EMBEDDING, 30),
            (LLMTaskKind.JUDGE_SCORING, 60),
            (LLMTaskKind.RESEARCH_ARCHITECTURE_SEED, 120),
        ],
    )
    def test_builtin_defaults_meet_minimums(self, kind: LLMTaskKind, minimum: int) -> None:
        llm = LLMSettings()
        assert resolve_llm_timeout_seconds(llm, kind, max_tokens=256) >= minimum
