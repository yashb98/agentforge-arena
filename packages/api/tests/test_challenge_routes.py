"""HTTP tests for challenge library routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import packages.api.src.routes.challenges as challenges_mod
from packages.api.src.routes.challenges import router


@pytest.fixture(autouse=True)
def clear_challenge_cache() -> object:
    challenges_mod._challenge_cache = None
    yield
    challenges_mod._challenge_cache = None


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_list_challenges_returns_items(client: TestClient) -> None:
    r = client.get("/api/v1/challenges")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 3
    assert len(body["challenges"]) == body["total"]


def test_get_challenge_by_id(client: TestClient) -> None:
    r = client.get("/api/v1/challenges/url-shortener-saas")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "url-shortener-saas"
    assert data["title"]


def test_get_challenge_404(client: TestClient) -> None:
    r = client.get("/api/v1/challenges/does-not-exist-xyz")
    assert r.status_code == 404


def test_parse_challenge_md_extracts_meta() -> None:
    md = """# Challenge: Demo

## Difficulty: Hard | Category: CLI Tool | Time: 45 minutes

## Brief

Hello world.

## Requirements

1. First thing
2. Second thing
"""
    from packages.api.src.routes.challenges import _parse_challenge_md

    out = _parse_challenge_md("demo", md)
    assert out.id == "demo"
    assert "Hello" in out.description
    assert len(out.requirements) >= 2
