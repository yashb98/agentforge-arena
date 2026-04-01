"""Hidden tests — URL Shortener redirect behavior."""

from __future__ import annotations

import httpx
import pytest


class TestRedirect:
    """GET /{code} — redirect to original URL."""

    def test_redirect_returns_301_or_302(self, client: httpx.Client, create_short_url: dict) -> None:
        code = create_short_url.get("short_code") or create_short_url.get("code", "")
        if not code:
            pytest.skip("Cannot extract short_code from create response")
        resp = client.get(f"/{code}")
        assert resp.status_code in (301, 302, 307, 308)

    def test_redirect_location_header(self, client: httpx.Client, sample_url: str, create_short_url: dict) -> None:
        code = create_short_url.get("short_code") or create_short_url.get("code", "")
        if not code:
            pytest.skip("Cannot extract short_code from create response")
        resp = client.get(f"/{code}")
        assert "location" in resp.headers
        assert resp.headers["location"] == sample_url

    def test_nonexistent_code_returns_404(self, client: httpx.Client) -> None:
        resp = client.get("/zzzz_nonexistent_code_12345")
        assert resp.status_code == 404

    def test_expired_url_returns_410(self, client: httpx.Client) -> None:
        """Create a URL with 1-second expiry, wait, then check."""
        import time

        resp = client.post("/shorten", json={
            "url": "https://example.com/will-expire",
            "expires_in_seconds": 1,
        })
        if resp.status_code not in (200, 201):
            pytest.skip("Expiration not supported")

        body = resp.json()
        code = body.get("short_code") or body.get("code", "")
        if not code:
            pytest.skip("Cannot extract short_code")

        time.sleep(2)
        resp = client.get(f"/{code}")
        # 410 Gone is ideal, 404 is acceptable
        assert resp.status_code in (404, 410)


class TestRedirectPerformance:
    """Performance tests for redirect latency."""

    def test_sequential_creates_under_10_seconds(self, client: httpx.Client) -> None:
        """100 URL creations should complete in <10 seconds."""
        import time

        start = time.monotonic()
        for i in range(100):
            resp = client.post("/shorten", json={"url": f"https://example.com/perf/{i}"})
            assert resp.status_code in (200, 201), f"Create #{i} failed: {resp.status_code}"
        elapsed = time.monotonic() - start
        assert elapsed < 10.0, f"100 creates took {elapsed:.1f}s (limit: 10s)"
