"""Shared fixtures for URL Shortener hidden test suite."""

from __future__ import annotations

import httpx
import pytest

BASE_URL = "http://localhost:8000"


@pytest.fixture()
def client() -> httpx.Client:
    """Synchronous HTTP client pointed at the team's running app."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as c:
        yield c


@pytest.fixture()
def async_client() -> httpx.AsyncClient:
    """Async HTTP client for concurrency tests."""
    return httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, follow_redirects=False)


@pytest.fixture()
def sample_url() -> str:
    return "https://example.com/some/long/path?query=value"


@pytest.fixture()
def create_short_url(client: httpx.Client, sample_url: str) -> dict:
    """Helper: create a short URL and return the response JSON."""
    resp = client.post("/shorten", json={"url": sample_url})
    assert resp.status_code in (200, 201), f"Create failed: {resp.status_code} {resp.text}"
    return resp.json()
