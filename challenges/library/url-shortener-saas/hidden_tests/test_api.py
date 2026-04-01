"""Hidden tests — URL Shortener API endpoints."""

from __future__ import annotations

import httpx
import pytest


class TestCreateShortURL:
    """POST /shorten — create a new short URL."""

    def test_create_returns_short_code(self, client: httpx.Client) -> None:
        resp = client.post("/shorten", json={"url": "https://example.com"})
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert "short_code" in body or "short_url" in body or "code" in body

    def test_create_with_custom_alias(self, client: httpx.Client) -> None:
        resp = client.post("/shorten", json={"url": "https://example.com", "custom_alias": "mylink"})
        assert resp.status_code in (200, 201)
        body = resp.json()
        # The custom alias should appear in the response
        short = body.get("short_code") or body.get("short_url") or body.get("code", "")
        assert "mylink" in str(short)

    def test_create_duplicate_alias_rejected(self, client: httpx.Client) -> None:
        payload = {"url": "https://example.com/a", "custom_alias": "dup_test_alias"}
        client.post("/shorten", json=payload)
        resp = client.post("/shorten", json={"url": "https://example.com/b", "custom_alias": "dup_test_alias"})
        assert resp.status_code in (400, 409, 422)

    def test_create_invalid_url_rejected(self, client: httpx.Client) -> None:
        resp = client.post("/shorten", json={"url": "not-a-valid-url"})
        assert resp.status_code in (400, 422)

    def test_create_empty_url_rejected(self, client: httpx.Client) -> None:
        resp = client.post("/shorten", json={"url": ""})
        assert resp.status_code in (400, 422)

    def test_create_missing_url_rejected(self, client: httpx.Client) -> None:
        resp = client.post("/shorten", json={})
        assert resp.status_code in (400, 422)

    def test_create_with_expiration(self, client: httpx.Client) -> None:
        resp = client.post("/shorten", json={
            "url": "https://example.com/expiring",
            "expires_in_seconds": 3600,
        })
        assert resp.status_code in (200, 201)


class TestHealthCheck:
    """GET /health — health check endpoint."""

    def test_health_returns_200(self, client: httpx.Client) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_json(self, client: httpx.Client) -> None:
        resp = client.get("/health")
        body = resp.json()
        assert "status" in body or "ok" in body or "healthy" in str(body).lower()


class TestListURLs:
    """GET /urls or GET /shorten — list created URLs."""

    def test_list_returns_array(self, client: httpx.Client) -> None:
        # Create at least one URL first
        client.post("/shorten", json={"url": "https://example.com/list-test"})
        # Try common list endpoints
        for path in ("/urls", "/shorten", "/links"):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                assert isinstance(body, (list, dict)), f"Expected list or dict from {path}"
                return
        pytest.skip("No list endpoint found at /urls, /shorten, or /links")


class TestDeleteURL:
    """DELETE /{code} — delete a short URL."""

    def test_delete_existing_url(self, client: httpx.Client, create_short_url: dict) -> None:
        code = create_short_url.get("short_code") or create_short_url.get("code", "")
        if not code:
            pytest.skip("Cannot extract short_code from create response")
        resp = client.delete(f"/{code}")
        assert resp.status_code in (200, 204, 404)

    def test_delete_nonexistent_returns_404(self, client: httpx.Client) -> None:
        resp = client.delete("/nonexistent_code_xyz_12345")
        assert resp.status_code in (404, 410)
