"""Hidden tests — Worker registration and task assignment."""

from __future__ import annotations

import httpx
import pytest

from conftest import submit_task


class TestWorkerRegistration:
    """Worker registration and polling."""

    def test_register_worker(self, client: httpx.Client) -> None:
        """POST /workers registers a new worker."""
        resp = client.post("/workers", json={"name": "test-worker-1"})
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert "id" in body or "worker_id" in body

    def test_worker_polls_for_task(self, client: httpx.Client) -> None:
        """Worker can poll and receive a task."""
        # Register worker
        reg = client.post("/workers", json={"name": "poll-worker"})
        if reg.status_code not in (200, 201):
            pytest.skip("Worker registration not implemented")
        worker = reg.json()
        worker_id = worker.get("id") or worker.get("worker_id", "")

        # Submit a task
        submit_task(client)

        # Poll for task
        for path in (
            f"/workers/{worker_id}/poll",
            "/tasks/next",
            "/queue/next",
        ):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                assert "id" in body or "task_id" in body
                return

        # Try POST-based polling
        for path in (f"/workers/{worker_id}/poll", "/tasks/claim"):
            resp = client.post(path)
            if resp.status_code == 200:
                return

        pytest.skip("No task polling endpoint found")

    def test_worker_completes_task(self, client: httpx.Client) -> None:
        """Worker can report task completion with result."""
        # Submit task
        created = submit_task(client)
        task_id = created.get("id") or created.get("task_id")

        # Report completion
        result_payload = {"result": {"output": "done"}, "status": "completed"}
        for path in (
            f"/tasks/{task_id}/complete",
            f"/tasks/{task_id}/result",
            f"/tasks/{task_id}",
        ):
            resp = client.post(path, json=result_payload)
            if resp.status_code in (200, 204):
                # Verify status changed
                status_resp = client.get(f"/tasks/{task_id}")
                if status_resp.status_code == 200:
                    body = status_resp.json()
                    assert body.get("status") in ("completed", "done", "finished")
                return

            # Try PUT/PATCH
            resp = client.put(path, json=result_payload)
            if resp.status_code in (200, 204):
                return

        pytest.skip("No task completion endpoint found")


class TestWorkerHeartbeat:
    """Worker heartbeat and stuck task recovery."""

    def test_worker_heartbeat(self, client: httpx.Client) -> None:
        """Worker can send heartbeat."""
        reg = client.post("/workers", json={"name": "hb-worker"})
        if reg.status_code not in (200, 201):
            pytest.skip("Worker registration not implemented")

        worker = reg.json()
        worker_id = worker.get("id") or worker.get("worker_id", "")

        for path in (
            f"/workers/{worker_id}/heartbeat",
            f"/workers/{worker_id}/ping",
        ):
            resp = client.post(path)
            if resp.status_code in (200, 204):
                return

        pytest.skip("No heartbeat endpoint found")
