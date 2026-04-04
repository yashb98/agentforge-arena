"""Circuit breaker behavior."""

from __future__ import annotations

import pytest

from packages.shared.src.reliability.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    circuit_breaker_http_guard,
)


@pytest.mark.asyncio
async def test_guard_records_success_and_resets_failures() -> None:
    b = CircuitBreaker("t", failure_threshold=3)
    calls = 0

    async def ok() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    out = await circuit_breaker_http_guard(b, ok, fallback=None, on_error=None)
    assert out == "ok"
    assert calls == 1
    assert b.state == CircuitState.CLOSED
    assert b._failures == 0


@pytest.mark.asyncio
async def test_guard_opens_after_threshold_failures() -> None:
    b = CircuitBreaker("t", failure_threshold=2, reset_timeout_seconds=3600.0)

    async def boom() -> None:
        raise RuntimeError("down")

    await circuit_breaker_http_guard(b, boom, fallback=None, on_error=None)
    assert b._failures == 1
    assert b.state == CircuitState.CLOSED

    await circuit_breaker_http_guard(b, boom, fallback=None, on_error=None)
    assert b.state == CircuitState.OPEN

    async def ok() -> str:
        return "nope"

    out = await circuit_breaker_http_guard(b, ok, fallback="skipped", on_error=None)
    assert out == "skipped"


@pytest.mark.asyncio
async def test_half_open_success_closes_circuit() -> None:
    b = CircuitBreaker("t", failure_threshold=99, reset_timeout_seconds=60.0, half_open_max_trials=1)
    b._state = CircuitState.HALF_OPEN
    b._half_open_trials = 0

    async def ok() -> str:
        return "recovered"

    out = await circuit_breaker_http_guard(b, ok, fallback=None, on_error=None)
    assert out == "recovered"
    assert b.state == CircuitState.CLOSED
