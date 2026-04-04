"""
AgentForge Arena — Tests for LLMClient

Tests the async LLM client, cost estimation, response parsing,
and Langfuse tracing integration. All HTTP calls are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from packages.shared.src.config import LLMSettings
from packages.shared.src.llm.client import (
    LLMClient,
    LLMResponse,
    LLMUsage,
    MODEL_PRICING,
    _estimate_cost,
)
from packages.shared.src.llm.task_timeout import LLMTaskKind


# ============================================================
# Fixtures
# ============================================================


def _make_openai_response(
    content: str = "Hello!",
    tool_calls: list | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> dict:
    """Build a mock OpenAI-format chat completion response."""
    message: dict = {"content": content, "role": "assistant"}
    if tool_calls:
        message["tool_calls"] = tool_calls

    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@pytest.fixture()
def mock_settings():
    """Minimal AppSettings-like object with real LLMSettings defaults."""
    settings = MagicMock()
    settings.llm = LLMSettings(
        litellm_proxy_url="http://localhost:4000",
        default_model="claude-sonnet-4-6",
    )
    return settings


# ============================================================
# Cost estimation tests
# ============================================================


class TestEstimateCost:
    """Test the _estimate_cost function."""

    def test_known_model_cost(self) -> None:
        """Known model uses its pricing."""
        usage = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
        cost = _estimate_cost("claude-opus-4-6", usage)
        # 15.0 input + 75.0 output = 90.0
        assert cost == 90.0

    def test_unknown_model_defaults_to_sonnet_pricing(self) -> None:
        """Unknown model falls back to default (3.0, 15.0) pricing."""
        usage = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
        cost = _estimate_cost("unknown-model-xyz", usage)
        # 3.0 + 15.0 = 18.0
        assert cost == 18.0

    def test_zero_tokens(self) -> None:
        """Zero tokens = zero cost."""
        cost = _estimate_cost("claude-sonnet-4-6", {})
        assert cost == 0.0

    def test_small_token_count(self) -> None:
        """Small token counts produce fractional costs."""
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        cost = _estimate_cost("claude-haiku-4-5", usage)
        # (1000/1M)*0.80 + (500/1M)*4.0 = 0.0008 + 0.002 = 0.0028
        assert cost == pytest.approx(0.0028, abs=1e-6)

    def test_all_known_models_have_pricing(self) -> None:
        """Every model in MODEL_PRICING returns a non-default cost."""
        for model in MODEL_PRICING:
            usage = {"prompt_tokens": 1000, "completion_tokens": 1000}
            cost = _estimate_cost(model, usage)
            assert cost > 0, f"{model} should have non-zero cost"


# ============================================================
# LLMClient tests
# ============================================================


class TestLLMClient:
    """Test LLMClient.completion() with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_completion_basic(self, mock_settings: MagicMock) -> None:
        """Basic completion returns parsed LLMResponse."""
        mock_response = httpx.Response(
            200,
            json=_make_openai_response(content="Test response"),
            request=httpx.Request("POST", "http://localhost:4000/v1/chat/completions"),
        )

        with patch("packages.shared.src.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=mock_response)

        result = await client.completion(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert isinstance(result, LLMResponse)
        assert result.content == "Test response"
        assert result.stop_reason == "stop"
        assert result.usage.prompt_tokens == 100
        assert result.usage.completion_tokens == 50
        assert result.usage.total_tokens == 150
        assert result.usage.cost_usd > 0
        assert result.usage.model == "claude-sonnet-4-6"
        assert result.usage.latency_ms > 0

    @pytest.mark.asyncio
    async def test_completion_explicit_timeout_override(self, mock_settings: MagicMock) -> None:
        """Explicit timeout_seconds is clamped and passed to HTTP layer."""
        mock_response = httpx.Response(
            200,
            json=_make_openai_response(),
            request=httpx.Request("POST", "http://localhost:4000/v1/chat/completions"),
        )

        with patch("packages.shared.src.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=mock_response)

        await client.completion(
            messages=[{"role": "user", "content": "Hi"}],
            timeout_seconds=9999,
        )
        post_timeout = client._http.post.call_args.kwargs["timeout"]
        assert post_timeout.read == mock_settings.llm.timeout_ceiling_seconds

        await client.completion(
            messages=[{"role": "user", "content": "Hi"}],
            timeout_seconds=3,
        )
        post_timeout_low = client._http.post.call_args.kwargs["timeout"]
        assert post_timeout_low.read == mock_settings.llm.timeout_floor_seconds

    @pytest.mark.asyncio
    async def test_completion_task_kind_changes_timeout(self, mock_settings: MagicMock) -> None:
        """Planning tasks resolve to longer read timeouts than DEFAULT."""
        mock_response = httpx.Response(
            200,
            json=_make_openai_response(),
            request=httpx.Request("POST", "http://localhost:4000/v1/chat/completions"),
        )

        with patch("packages.shared.src.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=mock_response)

        await client.completion(
            messages=[{"role": "user", "content": "x"}],
            task_kind=LLMTaskKind.DEFAULT,
            max_tokens=256,
        )
        t_default = client._http.post.call_args.kwargs["timeout"].read

        await client.completion(
            messages=[{"role": "user", "content": "x"}],
            task_kind=LLMTaskKind.AGENT_PLANNING_WRITE,
            max_tokens=256,
        )
        t_plan = client._http.post.call_args.kwargs["timeout"].read

        assert t_plan > t_default

    @pytest.mark.asyncio
    async def test_completion_with_model_override(self, mock_settings: MagicMock) -> None:
        """Model override is used instead of default."""
        mock_response = httpx.Response(
            200,
            json=_make_openai_response(),
            request=httpx.Request("POST", "http://localhost:4000/v1/chat/completions"),
        )

        with patch("packages.shared.src.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=mock_response)

        result = await client.completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="claude-opus-4-6",
        )

        assert result.usage.model == "claude-opus-4-6"
        # Verify the payload sent to proxy used the override model
        call_kwargs = client._http.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["model"] == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_completion_with_tool_calls(self, mock_settings: MagicMock) -> None:
        """Tool calls in response are parsed correctly."""
        tool_calls = [
            {
                "id": "call_abc123",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "test.py", "content": "print('hi')"}),
                },
            }
        ]
        mock_response = httpx.Response(
            200,
            json=_make_openai_response(
                content="",
                tool_calls=tool_calls,
                finish_reason="tool_calls",
            ),
            request=httpx.Request("POST", "http://localhost:4000/v1/chat/completions"),
        )

        with patch("packages.shared.src.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=mock_response)

        result = await client.completion(
            messages=[{"role": "user", "content": "Write a file"}],
            tools=[{"type": "function", "function": {"name": "write_file"}}],
        )

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["id"] == "call_abc123"
        assert result.tool_calls[0]["name"] == "write_file"
        assert result.stop_reason == "tool_calls"

    @pytest.mark.asyncio
    async def test_completion_sends_tools_in_payload(self, mock_settings: MagicMock) -> None:
        """Tools and tool_choice are included in the request payload."""
        mock_response = httpx.Response(
            200,
            json=_make_openai_response(),
            request=httpx.Request("POST", "http://localhost:4000/v1/chat/completions"),
        )

        with patch("packages.shared.src.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=mock_response)

        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        tool_choice = {"type": "function", "function": {"name": "test_tool"}}

        await client.completion(
            messages=[{"role": "user", "content": "Hello"}],
            tools=tools,
            tool_choice=tool_choice,
        )

        call_kwargs = client._http.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["tools"] == tools
        assert payload["tool_choice"] == tool_choice

    @pytest.mark.asyncio
    async def test_completion_with_langfuse_tracing(self, mock_settings: MagicMock) -> None:
        """Langfuse generation span is created and ended when configured."""
        mock_response = httpx.Response(
            200,
            json=_make_openai_response(),
            request=httpx.Request("POST", "http://localhost:4000/v1/chat/completions"),
        )

        mock_langfuse = MagicMock()
        mock_generation = MagicMock()
        mock_langfuse.generation.return_value = mock_generation

        with patch("packages.shared.src.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(langfuse=mock_langfuse)

        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=mock_response)

        await client.completion(
            messages=[{"role": "user", "content": "Hello"}],
            trace_name="test.trace",
            trace_metadata={"key": "value"},
        )

        mock_langfuse.generation.assert_called_once()
        mock_generation.end.assert_called_once()

    @pytest.mark.asyncio
    async def test_completion_without_langfuse(self, mock_settings: MagicMock) -> None:
        """Works fine without Langfuse configured."""
        mock_response = httpx.Response(
            200,
            json=_make_openai_response(),
            request=httpx.Request("POST", "http://localhost:4000/v1/chat/completions"),
        )

        with patch("packages.shared.src.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient(langfuse=None)

        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=mock_response)

        result = await client.completion(
            messages=[{"role": "user", "content": "Hello"}],
            trace_name="test.trace",
        )

        assert result.content == "Hello!"

    @pytest.mark.asyncio
    async def test_close(self, mock_settings: MagicMock) -> None:
        """Close properly closes the HTTP client."""
        with patch("packages.shared.src.llm.client.get_settings", return_value=mock_settings):
            client = LLMClient()

        client._http = AsyncMock()
        await client.close()
        client._http.aclose.assert_called_once()


# ============================================================
# LLMUsage / LLMResponse dataclass tests
# ============================================================


class TestDataclasses:
    """Test LLMUsage and LLMResponse defaults."""

    def test_llm_usage_defaults(self) -> None:
        usage = LLMUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.cost_usd == 0.0
        assert usage.model == ""

    def test_llm_response_defaults(self) -> None:
        resp = LLMResponse()
        assert resp.content == ""
        assert resp.tool_calls == []
        assert resp.stop_reason == ""
        assert isinstance(resp.usage, LLMUsage)
