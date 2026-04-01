"""Hidden tests — Task submission and status tracking."""

from __future__ import annotations

import time

import httpx
import pytest

from conftest import submit_task


class TestTaskSubmission:
    """POST /tasks — submit tasks to the queue."""

    def test_submit_returns_task_id(self, client: httpx.Client) -> None:
        body = submit_task(client)
        assert "id" in body or "task_id" in body

    def test_submit_with_priority(self, client: httpx.Client) -> None:
        for priority in ("high", "normal", "low"):
            body = submit_task(client, priority=priority)
            assert "id" in body or "task_id" in body

    def test_submit_invalid_payload_rejected(self, client: httpx.Client) -> None:
        resp = client.post("/tasks", json={})
        assert resp.status_code in (400, 422)

    def test_submit_returns_pending_status(self, client: httpx.Client) -> None:
        body = submit_task(client)
        status = body.get("status", "")
        assert status in ("pending", "queued", "submitted")


class TestTaskStatus:
    """GET /tasks/{id} — check task status."""

    def test_get_status_of_submitted_task(self, client: httpx.Client) -> None:
        created = submit_task(client)
        task_id = created.get("id") or created.get("task_id")
        assert task_id

        resp = client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body

    def test_get_nonexistent_task_returns_404(self, client: httpx.Client) -> None:
        resp = client.get("/tasks/nonexistent-task-id-xyz")
        assert resp.status_code == 404

    def test_status_transitions(self, client: httpx.Client) -> None:
        """Task should start as pending."""
        created = submit_task(client)
        task_id = created.get("id") or created.get("task_id")
        resp = client.get(f"/tasks/{task_id}")
        body = resp.json()
        assert body.get("status") in ("pending", "queued", "submitted", "running")


class TestTaskCancellation:
    """Cancel a pending task."""

    def test_cancel_pending_task(self, client: httpx.Client) -> None:
        created = submit_task(client)
        task_id = created.get("id") or created.get("task_id")

        for method in ("delete", "post"):
            if method == "delete":
                resp = client.delete(f"/tasks/{task_id}")
            else:
                resp = client.post(f"/tasks/{task_id}/cancel")
            if resp.status_code in (200, 204):
                return
        pytest.skip("No cancel endpoint found")

    def test_cancel_nonexistent_returns_404(self, client: httpx.Client) -> None:
        resp = client.delete("/tasks/nonexistent-xyz")
        if resp.status_code == 405:
            resp = client.post("/tasks/nonexistent-xyz/cancel")
        assert resp.status_code in (404, 410)


class TestPriorityOrdering:
    """Tasks with higher priority should be dequeued first."""

    def test_high_priority_dequeued_before_low(self, client: httpx.Client) -> None:
        """Submit low then high priority; high should be picked up first."""
        low = submit_task(client, payload={"type": "echo", "payload": {"order": "low"}}, priority="low")
        high = submit_task(client, payload={"type": "echo", "payload": {"order": "high"}}, priority="high")

        # Poll for next task (as a worker would)
        for path in ("/tasks/next", "/workers/poll", "/queue/next"):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                task_id = body.get("id") or body.get("task_id", "")
                high_id = high.get("id") or high.get("task_id", "")
                assert task_id == high_id, "High priority task should be dequeued first"
                return
        pytest.skip("No worker poll endpoint found")
