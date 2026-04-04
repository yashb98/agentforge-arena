"""Circuit breaker for external HTTP APIs (research, web, scholarly sources)."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and callers use strict mode."""


@dataclass
class CircuitBreaker:
    """Counts consecutive failures; opens to skip load until reset_timeout elapses."""

    name: str
    failure_threshold: int = 5
    reset_timeout_seconds: float = 60.0
    half_open_max_trials: int = 1
    _failures: int = 0
    _opened_at: float | None = None
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _half_open_trials: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        if (
            self._state == CircuitState.OPEN
            and self._opened_at is not None
            and time.monotonic() - self._opened_at >= self.reset_timeout_seconds
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_trials = 0
            logger.info("Circuit %s half-open after cooldown", self.name)
        return self._state

    def allow_request(self) -> bool:
        st = self.state
        if st == CircuitState.CLOSED:
            return True
        if st == CircuitState.HALF_OPEN:
            return self._half_open_trials < self.half_open_max_trials
        return False

    def record_success(self) -> None:
        self._failures = 0
        if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            logger.info("Circuit %s closed after success", self.name)
        self._state = CircuitState.CLOSED
        self._opened_at = None
        self._half_open_trials = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._state == CircuitState.HALF_OPEN:
            self._opened_at = time.monotonic()
            self._state = CircuitState.OPEN
            self._half_open_trials = 0
            logger.warning("Circuit %s opened from half-open after failure", self.name)
            return
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit %s opened after %d failures",
                self.name,
                self._failures,
            )

    def note_half_open_attempt(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self._half_open_trials += 1


async def circuit_breaker_http_guard(
    breaker: CircuitBreaker,
    factory: Callable[[], Awaitable[T]],
    *,
    fallback: T | None = None,
    on_error: T | None = None,
    strict: bool = False,
) -> T | None:
    """
    Run an async HTTP call under the breaker.

    - When open: returns ``fallback``.
    - On exception: ``record_failure``; returns ``on_error`` if set, else re-raises
      when ``strict`` is True, otherwise returns ``on_error`` / ``fallback``.
    - On success: ``record_success`` and returns the result.
    """
    if not breaker.allow_request():
        logger.debug("Circuit %s skipping request (state=%s)", breaker.name, breaker.state)
        return fallback

    if breaker.state == CircuitState.HALF_OPEN:
        breaker.note_half_open_attempt()

    try:
        result = await factory()
    except Exception:
        breaker.record_failure()
        if strict:
            raise
        return on_error if on_error is not None else fallback
    else:
        breaker.record_success()
        return result
