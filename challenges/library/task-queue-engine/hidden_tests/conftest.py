"""Shared fixtures for Task Queue Engine hidden test suite."""

from __future__ import annotations

import uuid

import httpx
import pytest

BASE_URL = "http://localhost:8000"


@pytest.fixture()
def client() -> httpx.Client:
    """Synchronous HTTP client."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


@pytest.fixture()
def async_client() -> httpx.AsyncClient:
    """Async HTTP client for concurrency tests."""
    return httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)


@pytest.fixture()
def sample_task_payload() -> dict:
    """A sample task payload."""
    return {
        "type": "process_data",
        "payload": {"input": f"test-data-{uuid.uuid4().hex[:8]}"},
    }


def submit_task(client: httpx.Client, payload: dict | None = None, priority: str = "normal") -> dict:
    """Helper: submit a task and return the response."""
    body = payload or {"type": "echo", "payload": {"message": "hello"}}
    body["priority"] = priority
    resp = client.post("/tasks", json=body)
    assert resp.status_code in (200, 201, 202), f"Submit failed: {resp.status_code} {resp.text}"
    return resp.json()
