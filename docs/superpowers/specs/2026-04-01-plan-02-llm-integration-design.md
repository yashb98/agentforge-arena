# Plan 2: LLM Integration via LiteLLM

> Full spec — creates an async LLM client wrapper, wires agent message processing to call LLMs, connects LLM judges, and adds budget tracking with Langfuse tracing.

## Problem Statement

The platform has no LLM calls anywhere:
- `AgentProcess._process_message()` (manager.py:119) has a TODO — agents can't think
- `LLMJudge` (service.py:206) is initialized with `llm_client=None` — subjective judging returns hardcoded 50.0
- No budget tracking — `tournament.total_cost_usd` never updates
- No Langfuse tracing integration for LLM calls

## Architecture

```
LiteLLM Proxy (docker-compose)
    ^
    |  HTTP (OpenAI-compatible API)
    |
LLMClient (packages/shared/src/llm/client.py)
    ├── completion() → generic async LLM call with retry + tracing
    ├── tool_use() → forced tool_use call for structured output
    └── tracks: tokens, cost, latency per call
    ^
    |  Injected via Depends() or constructor
    |
    ├── AgentProcess._process_message()  → role-specific LLM calls
    ├── LLMJudge.judge_*()               → evaluation calls (temp=0)
    └── Budget tracker                    → updates tournament cost
```

## Changes Required

### Step 1: Create `packages/shared/src/llm/client.py`

New file — async LiteLLM wrapper with Langfuse tracing:

```python
"""Async LLM client wrapping LiteLLM with Langfuse tracing and budget tracking."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel

from packages.shared.src.config import get_settings

logger = logging.getLogger(__name__)


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
    """Async LLM client using LiteLLM proxy."""

    def __init__(
        self,
        langfuse: object | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = settings.llm.litellm_proxy_url
        self._default_model = settings.llm.default_model
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
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
    ) -> LLMResponse:
        """Make an LLM completion call via LiteLLM proxy."""
        import time

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

        # Langfuse trace
        generation = None
        if self._langfuse and trace_name:
            generation = self._langfuse.generation(
                name=trace_name,
                model=resolved_model,
                input=messages,
                metadata=trace_metadata or {},
            )

        resp = await self._http.post("/v1/chat/completions", json=payload)
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
            cost_usd=self._estimate_cost(resolved_model, usage_data),
            model=resolved_model,
            latency_ms=latency_ms,
        )

        # Parse tool calls if present
        tool_calls = []
        if choice["message"].get("tool_calls"):
            for tc in choice["message"]["tool_calls"]:
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                })

        result = LLMResponse(
            content=choice["message"].get("content", "") or "",
            tool_calls=tool_calls,
            stop_reason=choice.get("finish_reason", ""),
            usage=usage,
            raw=data,
        )

        # Complete Langfuse trace
        if generation:
            generation.end(
                output=result.content or str(tool_calls),
                usage={
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
            )

        logger.debug(
            "LLM call: model=%s tokens=%d cost=$%.4f latency=%dms",
            resolved_model, usage.total_tokens, usage.cost_usd, latency_ms,
        )

        return result

    async def close(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _estimate_cost(model: str, usage: dict) -> float:
        """Rough cost estimation per model. LiteLLM also tracks this."""
        # Prices per 1M tokens (input/output)
        PRICING = {
            "claude-opus-4-6": (15.0, 75.0),
            "claude-sonnet-4-6": (3.0, 15.0),
            "claude-haiku-4-5": (0.80, 4.0),
            "gpt-5": (10.0, 30.0),
        }
        rates = PRICING.get(model, (3.0, 15.0))  # default to Sonnet pricing
        input_cost = (usage.get("prompt_tokens", 0) / 1_000_000) * rates[0]
        output_cost = (usage.get("completion_tokens", 0) / 1_000_000) * rates[1]
        return round(input_cost + output_cost, 6)
```

### Step 2: Create `packages/shared/src/llm/__init__.py`

Empty `__init__.py` to make it a package.

### Step 3: Add `get_llm_client()` dependency in `dependencies.py`

```python
from packages.shared.src.llm.client import LLMClient

def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client
```

### Step 4: Initialize LLMClient in lifespan (`main.py`)

After Langfuse init:

```python
from packages.shared.src.llm.client import LLMClient

app.state.llm_client = LLMClient(
    langfuse=getattr(app.state, "langfuse", None),
)
```

Shutdown:
```python
if hasattr(app.state, "llm_client"):
    await app.state.llm_client.close()
```

### Step 5: Wire `AgentProcess._process_message()` to LLM

This is the critical change. Replace the TODO with actual LLM routing:

```python
class AgentProcess:
    def __init__(
        self,
        agent: Agent,
        system_prompt: str,
        workspace_path: str,
        llm_client: LLMClient,
        mailbox: object,  # RedisMailbox (Plan 4) or file-based for now
    ) -> None:
        self.agent = agent
        self.system_prompt = system_prompt
        self.workspace_path = workspace_path
        self._llm = llm_client
        self._mailbox = mailbox
        self._conversation: list[dict[str, Any]] = []  # Running conversation history
        self._task: asyncio.Task | None = None

    async def _process_message(self, message: AgentMessage) -> None:
        """Process a message by calling the LLM with role context."""
        self.agent.actions_count += 1

        # Build the user message from the agent message
        user_content = (
            f"[{message.message_type.value}] from {message.from_agent.value}:\n"
            f"{json.dumps(message.payload, default=str, indent=2)}"
        )

        self._conversation.append({"role": "user", "content": user_content})

        # Call LLM
        response = await self._llm.completion(
            messages=[
                {"role": "system", "content": self.system_prompt},
                *self._conversation,
            ],
            model=self.agent.model.value,
            temperature=0.3,
            max_tokens=8192,
            trace_name=f"agent.{self.agent.role.value}.process",
            trace_metadata={
                "team_id": str(self.agent.team_id),
                "tournament_id": str(self.agent.tournament_id),
                "message_type": message.message_type.value,
            },
        )

        # Track usage
        self.agent.total_tokens_used += response.usage.total_tokens
        self.agent.total_cost_usd += response.usage.cost_usd

        # Append assistant response to conversation
        self._conversation.append({"role": "assistant", "content": response.content})

        # Trim conversation to prevent context overflow (keep last 20 turns)
        if len(self._conversation) > 40:
            self._conversation = self._conversation[-40:]

        logger.info(
            "Agent %s processed message: tokens=%d cost=$%.4f",
            self.agent.role.value,
            response.usage.total_tokens,
            response.usage.cost_usd,
        )
```

**Note:** Tool use (sandbox bash, file write, etc.) is a future enhancement. This wiring gets the basic LLM call working. Tool use will be added when sandbox integration is complete.

### Step 6: Wire `LLMJudge` to use `LLMClient`

```python
class LLMJudge:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def judge_ux_design(self, workspace_path: str) -> JudgeScore:
        # Read frontend files for context
        prompt = """You are a senior UX reviewer judging a hackathon project.
        ... (existing prompt) ...
        Respond with ONLY a JSON object: {"score": <0-100>, "details": "<explanation>"}"""

        response = await self._llm.completion(
            messages=[{"role": "user", "content": prompt}],
            model="claude-opus-4-6",
            temperature=0.0,  # Deterministic judging
            max_tokens=1024,
            trace_name="judge.ux_design",
        )

        # Parse JSON from response
        import json
        try:
            result = json.loads(response.content)
            score = float(result["score"])
            details = result["details"]
        except (json.JSONDecodeError, KeyError, ValueError):
            score = 50.0
            details = f"Failed to parse LLM response: {response.content[:200]}"

        return JudgeScore(
            dimension="ux_design",
            score=min(max(score, 0.0), 100.0),
            weight=SCORING_WEIGHTS["ux_design"],
            judge_type="llm",
            details=details,
        )

    # Same pattern for judge_architecture() and judge_innovation()
```

### Step 7: Wire `JudgeService` to accept `LLMClient`

```python
class JudgeService:
    def __init__(self, event_bus: EventBus, sandbox_manager: object, llm_client: LLMClient) -> None:
        self._events = event_bus
        self._sandbox = sandbox_manager
        self._automated = AutomatedJudge()
        self._llm = LLMJudge(llm_client=llm_client)
```

Update lifespan initialization (Plan 1) to pass `llm_client`:
```python
app.state.judge_service = JudgeService(
    event_bus=app.state.event_bus,
    sandbox_manager=app.state.sandbox_manager,
    llm_client=app.state.llm_client,
)
```

### Step 8: Add budget tracking

The orchestrator's `_check_budget()` already publishes warnings. We need to aggregate agent costs up to the tournament level.

Add an event handler in the orchestrator that listens for agent cost updates:

```python
# In AgentProcess, after each LLM call, publish cost event:
await self._events.publish(
    "agent.cost.updated",
    source="agents.process",
    tournament_id=self.agent.tournament_id,
    team_id=self.agent.team_id,
    agent_id=self.agent.id,
    payload={
        "tokens_used": response.usage.total_tokens,
        "cost_usd": response.usage.cost_usd,
    },
)
```

The orchestrator can subscribe to this to update `tournament.total_cost_usd`. For now, a simpler approach: the health monitor aggregates costs from all agents on each check cycle.

### Step 9: Add LiteLLM config to settings

Update `packages/shared/src/config.py` if not already present:

```python
class LLMSettings(BaseModel):
    litellm_proxy_url: str = "http://localhost:4000"
    default_model: str = "claude-sonnet-4-6"
    budget_per_tournament_usd: float = 500.0
    budget_alert_threshold: float = 0.80
    max_retries: int = 3
    timeout_seconds: int = 120
```

## Files Created

| File | Purpose |
|------|---------|
| `packages/shared/src/llm/__init__.py` | Package init |
| `packages/shared/src/llm/client.py` | Async LLM client with tracing + cost tracking |

## Files Modified

| File | Change |
|------|--------|
| `packages/api/src/main.py` | Init LLMClient in lifespan, pass to services |
| `packages/api/src/dependencies.py` | Add `get_llm_client()` provider |
| `packages/agents/src/teams/manager.py` | Wire `_process_message()` to LLM, accept LLMClient |
| `packages/judge/src/scoring/service.py` | Wire LLMJudge to LLMClient, parse JSON responses |
| `packages/shared/src/config.py` | Ensure LLM settings are complete |

## Dependencies

- **Depends on Plan 1** — services must be initialized in lifespan first
- LiteLLM proxy must be running (docker-compose already has it)
- Langfuse is optional (graceful degradation if not available)

## Testing Strategy

1. **Unit test LLMClient** — mock httpx, verify request payload, response parsing, cost estimation
2. **Unit test AgentProcess with LLM** — mock LLMClient, verify conversation building and token tracking
3. **Unit test LLMJudge** — mock LLMClient, verify JSON parsing, score clamping, error fallback
4. **Integration test** — with real LiteLLM proxy, verify end-to-end LLM call (mark as `@pytest.mark.integration`)

### Test files:
- `packages/shared/tests/test_llm_client.py`
- `packages/agents/tests/test_agent_llm.py`
- `packages/judge/tests/test_llm_judge.py`

## Acceptance Criteria

- [ ] `LLMClient.completion()` makes HTTP calls to LiteLLM proxy and returns parsed responses
- [ ] `AgentProcess._process_message()` calls LLM with system prompt + conversation history
- [ ] Agent token usage and cost are tracked per agent (`agent.total_tokens_used`, `agent.total_cost_usd`)
- [ ] `LLMJudge.judge_ux_design()` returns real LLM-evaluated scores (not hardcoded 50.0)
- [ ] `LLMJudge.judge_architecture()` returns real LLM-evaluated scores
- [ ] `LLMJudge.judge_innovation()` returns real LLM-evaluated scores
- [ ] LLM judge uses `temperature=0` for reproducibility
- [ ] Langfuse traces are created for each LLM call (when Langfuse is enabled)
- [ ] Cost estimation works for all supported models
- [ ] Conversation history is trimmed to prevent context overflow
- [ ] Graceful error handling when LLM call fails (retry, then structured error)
