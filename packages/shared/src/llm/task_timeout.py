"""
Per-task HTTP read timeouts for LLM calls.

Timeouts are chosen from LLMSettings by task kind, then adjusted for max_tokens,
tool rounds, and optional per-agent ceilings from AgentConfig.timeout_seconds.
"""

from __future__ import annotations

from enum import StrEnum

from packages.shared.src.types.models import AgentMessage, AgentRole, MessageType


class LLMTaskKind(StrEnum):
    """Semantic category for timeout and observability."""

    DEFAULT = "default"
    AGENT_TOOL_LOOP = "agent_tool_loop"
    AGENT_PLANNING_WRITE = "agent_planning_write"
    AGENT_REVIEW = "agent_review"
    AGENT_RESEARCH_SYNTHESIS = "agent_research_synthesis"
    RESEARCH_PEER_REVIEW = "research_peer_review"
    RESEARCH_ARCHITECTURE_SEED = "research_architecture_seed"
    JUDGE_SCORING = "judge_scoring"
    MEMORY_EMBEDDING = "memory_embedding"
    MEMORY_COMPRESSION = "memory_compression"


def infer_agent_llm_task_kind(message: AgentMessage, *, role: AgentRole) -> LLMTaskKind:
    """Map mailbox message + role to an LLM task kind for timeout selection."""
    mt = message.message_type
    if mt in (MessageType.REVIEW_REQUEST, MessageType.REVIEW_FEEDBACK):
        return LLMTaskKind.AGENT_REVIEW
    if mt == MessageType.ARCHITECTURE_UPDATE:
        return LLMTaskKind.AGENT_PLANNING_WRITE
    if role == AgentRole.RESEARCHER:
        return LLMTaskKind.AGENT_RESEARCH_SYNTHESIS
    # Status/help/bugs/fixes: multi-step tool use, same bucket as normal build work
    return LLMTaskKind.AGENT_TOOL_LOOP


def _base_seconds_for_kind(llm: object, kind: LLMTaskKind) -> int:
    """Read per-kind base timeout from LLMSettings-like object."""
    mapping: dict[LLMTaskKind, str] = {
        LLMTaskKind.DEFAULT: "timeout_seconds",
        LLMTaskKind.AGENT_TOOL_LOOP: "timeout_agent_tools_seconds",
        LLMTaskKind.AGENT_PLANNING_WRITE: "timeout_agent_planning_seconds",
        LLMTaskKind.AGENT_REVIEW: "timeout_agent_review_seconds",
        LLMTaskKind.AGENT_RESEARCH_SYNTHESIS: "timeout_agent_research_seconds",
        LLMTaskKind.RESEARCH_PEER_REVIEW: "timeout_research_peer_review_seconds",
        LLMTaskKind.RESEARCH_ARCHITECTURE_SEED: "timeout_research_architecture_seed_seconds",
        LLMTaskKind.JUDGE_SCORING: "timeout_judge_seconds",
        LLMTaskKind.MEMORY_EMBEDDING: "timeout_embedding_seconds",
        LLMTaskKind.MEMORY_COMPRESSION: "timeout_compression_seconds",
    }
    attr = mapping[kind]
    raw = getattr(llm, attr, None)
    if isinstance(raw, int):
        return raw
    return int(getattr(llm, "timeout_seconds", 60))


def resolve_llm_timeout_seconds(
    llm: object,
    kind: LLMTaskKind,
    *,
    max_tokens: int = 8192,
    has_tools: bool = False,
    tool_round_index: int = 0,
    agent_timeout_ceiling: int | None = None,
) -> int:
    """Compute HTTP read timeout (seconds) for one completion request.

    - Starts from per-kind base in settings.
    - Adds a bounded bump from ``max_tokens`` (longer generations need more wall time).
    - Adds a small bump per tool round (later rounds carry larger chat history).
    - If ``has_tools`` and kind is agent-side, ensures at least ``timeout_agent_tools_floor``.
    - Applies ``agent_timeout_ceiling`` when set (from ``AgentConfig.timeout_seconds``).
    - Clamps to [``timeout_floor_seconds``, ``timeout_ceiling_seconds``] on settings.
    """
    base = _base_seconds_for_kind(llm, kind)

    mt = max(256, int(max_tokens))
    # ~1s extra per 512 completion tokens, capped
    token_bump = min(180, max(0, (mt - 256) // 512))

    round_bump = min(90, max(0, int(tool_round_index)) * 12)

    resolved = base + token_bump + round_bump

    floor = int(getattr(llm, "timeout_floor_seconds", 10))
    ceiling = int(getattr(llm, "timeout_ceiling_seconds", 900))

    if has_tools and kind in (
        LLMTaskKind.AGENT_TOOL_LOOP,
        LLMTaskKind.AGENT_REVIEW,
        LLMTaskKind.AGENT_PLANNING_WRITE,
        LLMTaskKind.AGENT_RESEARCH_SYNTHESIS,
    ):
        tool_floor = int(getattr(llm, "timeout_agent_tools_floor", 45))
        resolved = max(resolved, tool_floor)

    resolved = max(floor, min(resolved, ceiling))

    if agent_timeout_ceiling is not None:
        cap = int(agent_timeout_ceiling)
        # Sub-floor ceilings are raised to floor so HTTP stays viable.
        effective_cap = max(floor, min(cap, ceiling))
        resolved = min(resolved, effective_cap)

    return max(floor, min(resolved, ceiling))
