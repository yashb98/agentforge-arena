"""Hidden tests — URL Shortener analytics."""

from __future__ import annotations

import httpx
import pytest


class TestAnalytics:
    """Analytics endpoint tests."""

    def test_click_count_increments(self, client: httpx.Client, create_short_url: dict) -> None:
        """Clicking a URL should increment the analytics counter."""
        code = create_short_url.get("short_code") or create_short_url.get("code", "")
        if not code:
            pytest.skip("Cannot extract short_code")

        # Click the URL 3 times
        for _ in range(3):
            client.get(f"/{code}")

        # Check analytics — try common endpoints
        for path in (f"/analytics/{code}", f"/{code}/stats", f"/{code}/analytics"):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                clicks = body.get("clicks") or body.get("click_count") or body.get("total_clicks", 0)
                assert clicks >= 3, f"Expected >=3 clicks, got {clicks}"
                return

        pytest.skip("No analytics endpoint found")

    def test_analytics_for_nonexistent_code(self, client: httpx.Client) -> None:
        """Analytics for non-existent code should return 404."""
        for path in (
            "/analytics/nonexistent_xyz",
            "/nonexistent_xyz/stats",
            "/nonexistent_xyz/analytics",
        ):
            resp = client.get(path)
            if resp.status_code != 405:  # Skip method-not-allowed
                assert resp.status_code in (404, 410)
                return

    def test_analytics_contains_metadata(self, client: httpx.Client, create_short_url: dict) -> None:
        """Analytics response should include useful metadata."""
        code = create_short_url.get("short_code") or create_short_url.get("code", "")
        if not code:
            pytest.skip("Cannot extract short_code")

        # Click once to generate data
        client.get(f"/{code}")

        for path in (f"/analytics/{code}", f"/{code}/stats", f"/{code}/analytics"):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                # Should have at least clicks and some form of URL info
                has_clicks = any(k in body for k in ("clicks", "click_count", "total_clicks"))
                has_url = any(k in body for k in ("url", "original_url", "long_url", "target"))
                assert has_clicks, f"Analytics missing click data: {body.keys()}"
                assert has_url, f"Analytics missing URL info: {body.keys()}"
                return

        pytest.skip("No analytics endpoint found")


class TestAnalyticsConcurrency:
    """Concurrent click tracking accuracy."""

    @pytest.mark.asyncio
    async def test_concurrent_clicks_counted(self, async_client: httpx.AsyncClient) -> None:
        """50 concurrent clicks should all be counted."""
        import asyncio

        # Create a URL
        resp = await async_client.post("/shorten", json={"url": "https://example.com/concurrent-test"})
        if resp.status_code not in (200, 201):
            pytest.skip("Create failed")

        body = resp.json()
        code = body.get("short_code") or body.get("code", "")
        if not code:
            pytest.skip("Cannot extract short_code")

        # Fire 50 concurrent clicks
        tasks = [async_client.get(f"/{code}") for _ in range(50)]
        await asyncio.gather(*tasks)

        # Check count — try common endpoints
        for path in (f"/analytics/{code}", f"/{code}/stats", f"/{code}/analytics"):
            resp = await async_client.get(path)
            if resp.status_code == 200:
                data = resp.json()
                clicks = data.get("clicks") or data.get("click_count") or data.get("total_clicks", 0)
                assert clicks >= 45, f"Expected >=45 clicks (of 50), got {clicks}"
                await async_client.aclose()
                return

        await async_client.aclose()
        pytest.skip("No analytics endpoint found")
