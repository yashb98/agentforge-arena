"""
AgentForge Arena — Async LLM Client

Wraps LiteLLM proxy with Langfuse tracing and cost tracking.
All LLM calls in the platform go through this client.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from packages.shared.src.config import get_settings
from packages.shared.src.llm.task_timeout import LLMTaskKind, resolve_llm_timeout_seconds

logger = logging.getLogger(__name__)


# Cost per 1M tokens (input, output) in USD
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
    "gpt-5": (10.0, 30.0),
    "gemini-3-pro": (3.5, 10.5),
    "qwen3-72b": (0.90, 0.90),
    "qwen3-32b": (0.40, 0.40),
    "qwen3-8b": (0.20, 0.20),
}


@dataclass
class LLMUsage:
    """Token usage and cost from a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    latency_ms: float = 0.0


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    usage: LLMUsage = field(default_factory=LLMUsage)
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """Async LLM client using LiteLLM proxy (OpenAI-compatible API)."""

    def __init__(self, langfuse: object | None = None) -> None:
        settings = get_settings()
        self._base_url = settings.llm.litellm_proxy_url.rstrip("/")
        self._default_model = settings.llm.default_model
        ceiling = float(settings.llm.timeout_ceiling_seconds)
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(ceiling, connect=10.0),
        )
        self._langfuse = langfuse

    async def completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 8192,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        trace_name: str | None = None,
        trace_metadata: dict[str, Any] | None = None,
        task_kind: LLMTaskKind | None = None,
        timeout_seconds: int | None = None,
        agent_timeout_ceiling: int | None = None,
        tool_round_index: int = 0,
    ) -> LLMResponse:
        """Make an LLM completion call via LiteLLM proxy.

        Args:
            messages: Chat messages in OpenAI format.
            model: Model ID override (defaults to settings.llm.default_model).
            temperature: Sampling temperature.
            max_tokens: Maximum completion tokens.
            tools: Tool definitions for function calling.
            tool_choice: Tool selection strategy.
            trace_name: Langfuse trace name for observability.
            trace_metadata: Additional metadata for the Langfuse trace.
            task_kind: When set (and ``timeout_seconds`` is not), picks base timeout from settings.
            timeout_seconds: Explicit HTTP read timeout for this request (clamped to settings floor/ceiling).
            agent_timeout_ceiling: Optional cap from ``AgentConfig.timeout_seconds`` (arena agents).
            tool_round_index: Multi-tool agent loop index; larger contexts get slightly more time.

        Returns:
            Parsed LLMResponse with content, tool_calls, usage, and cost.

        Raises:
            httpx.HTTPStatusError: If the LLM proxy returns an error.
        """
        llm_settings = get_settings().llm
        if timeout_seconds is not None:
            lo = llm_settings.timeout_floor_seconds
            hi = llm_settings.timeout_ceiling_seconds
            resolved_read = max(lo, min(int(timeout_seconds), hi))
        else:
            kind = task_kind or LLMTaskKind.DEFAULT
            resolved_read = resolve_llm_timeout_seconds(
                llm_settings,
                kind,
                max_tokens=max_tokens,
                has_tools=bool(tools),
                tool_round_index=tool_round_index,
                agent_timeout_ceiling=agent_timeout_ceiling,
            )

        resolved_model = model or self._default_model
        start = time.monotonic()

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        # Langfuse generation span
        generation = None
        trace_meta = dict(trace_metadata or {})
        trace_meta["llm_http_timeout_seconds"] = resolved_read

        if self._langfuse and trace_name:
            try:
                generation = self._langfuse.generation(  # type: ignore[union-attr]
                    name=trace_name,
                    model=resolved_model,
                    input=messages,
                    metadata=trace_meta,
                )
            except Exception:
                logger.debug("Langfuse generation creation failed", exc_info=True)

        req_timeout = httpx.Timeout(resolved_read, connect=10.0)
        resp = await self._http.post(
            "/v1/chat/completions",
            json=payload,
            timeout=req_timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        latency_ms = (time.monotonic() - start) * 1000

        # Parse response
        choice = data["choices"][0]
        usage_data = data.get("usage", {})

        usage = LLMUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            cost_usd=_estimate_cost(resolved_model, usage_data),
            model=resolved_model,
            latency_ms=latency_ms,
        )

        # Parse tool calls
        tool_calls: list[dict[str, Any]] = []
        raw_tool_calls = choice.get("message", {}).get("tool_calls")
        if raw_tool_calls:
            for tc in raw_tool_calls:
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                })

        result = LLMResponse(
            content=choice.get("message", {}).get("content", "") or "",
            tool_calls=tool_calls,
            stop_reason=choice.get("finish_reason", ""),
            usage=usage,
            raw=data,
        )

        # Complete Langfuse span
        if generation:
            try:
                generation.end(  # type: ignore[union-attr]
                    output=result.content or json.dumps(tool_calls),
                    usage={
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "total_tokens": usage.total_tokens,
                    },
                )
            except Exception:
                logger.debug("Langfuse generation end failed", exc_info=True)

        logger.debug(
            "LLM call: model=%s tokens=%d cost=$%.4f latency=%dms",
            resolved_model,
            usage.total_tokens,
            usage.cost_usd,
            int(latency_ms),
        )

        return result

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()


def _estimate_cost(model: str, usage: dict[str, Any]) -> float:
    """Estimate USD cost from token usage and model pricing."""
    rates = MODEL_PRICING.get(model, (3.0, 15.0))  # default to Sonnet pricing
    input_cost = (usage.get("prompt_tokens", 0) / 1_000_000) * rates[0]
    output_cost = (usage.get("completion_tokens", 0) / 1_000_000) * rates[1]
    return round(input_cost + output_cost, 6)
