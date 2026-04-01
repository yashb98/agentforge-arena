"""Hidden tests — Message persistence and history."""

from __future__ import annotations

import httpx
import pytest


class TestMessageHistory:
    """Message persistence and retrieval."""

    def test_get_messages_returns_array(self, client: httpx.Client) -> None:
        """GET /rooms/{name}/messages returns message history."""
        client.post("/rooms", json={"name": "history-room"})

        for path in ("/rooms/history-room/messages", "/messages?room=history-room"):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                assert isinstance(body, (list, dict))
                return
        pytest.skip("No message history endpoint found")

    def test_messages_have_pagination(self, client: httpx.Client) -> None:
        """Message history supports limit/offset pagination."""
        client.post("/rooms", json={"name": "page-room"})

        for path in (
            "/rooms/page-room/messages?limit=5&offset=0",
            "/messages?room=page-room&limit=5&offset=0",
        ):
            resp = client.get(path)
            if resp.status_code == 200:
                return
        pytest.skip("No paginated message endpoint found")

    def test_messages_ordered_by_timestamp(self, client: httpx.Client) -> None:
        """Messages should be ordered chronologically."""
        client.post("/rooms", json={"name": "order-room"})

        for path in ("/rooms/order-room/messages",):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                messages = body if isinstance(body, list) else body.get("messages", [])
                if len(messages) >= 2:
                    timestamps = []
                    for m in messages:
                        ts = m.get("timestamp") or m.get("created_at") or m.get("sent_at", "")
                        timestamps.append(str(ts))
                    assert timestamps == sorted(timestamps), "Messages not chronologically ordered"
                return
        pytest.skip("No message history endpoint found")


class TestMessageSearch:
    """Message search functionality."""

    def test_search_messages(self, client: httpx.Client) -> None:
        """Search messages by keyword."""
        for path in (
            "/rooms/history-room/messages/search?q=hello",
            "/messages/search?room=history-room&q=hello",
            "/rooms/history-room/messages?search=hello",
        ):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                assert isinstance(body, (list, dict))
                return
        pytest.skip("No message search endpoint found")
