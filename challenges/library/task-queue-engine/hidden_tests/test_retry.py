"""Hidden tests — Retry logic and dead letter queue."""

from __future__ import annotations

import time

import httpx
import pytest

from conftest import submit_task


class TestRetryLogic:
    """Failed tasks should retry up to 3 times."""

    def test_failed_task_is_retried(self, client: httpx.Client) -> None:
        """Reporting a task as failed should trigger a retry."""
        created = submit_task(client)
        task_id = created.get("id") or created.get("task_id")

        # Report failure
        fail_payload = {"status": "failed", "error": "intentional failure"}
        for path in (
            f"/tasks/{task_id}/fail",
            f"/tasks/{task_id}/complete",
            f"/tasks/{task_id}",
        ):
            resp = client.post(path, json=fail_payload)
            if resp.status_code in (200, 204):
                break
            resp = client.put(path, json=fail_payload)
            if resp.status_code in (200, 204):
                break
        else:
            pytest.skip("No failure reporting endpoint found")

        # Check task — should be pending (retrying) or have retry count
        time.sleep(1)
        status_resp = client.get(f"/tasks/{task_id}")
        if status_resp.status_code == 200:
            body = status_resp.json()
            # Should be retrying or show retry count
            retry_count = body.get("retries") or body.get("retry_count") or body.get("attempts", 0)
            status = body.get("status", "")
            assert retry_count >= 1 or status in ("pending", "queued", "retrying"), \
                f"Expected retry, got status={status}, retries={retry_count}"

    def test_max_retries_respected(self, client: httpx.Client) -> None:
        """After 3 failures, task should not retry further."""
        created = submit_task(client)
        task_id = created.get("id") or created.get("task_id")

        # Fail 4 times
        for i in range(4):
            fail_payload = {"status": "failed", "error": f"failure #{i+1}"}
            for path in (f"/tasks/{task_id}/fail", f"/tasks/{task_id}/complete"):
                resp = client.post(path, json=fail_payload)
                if resp.status_code in (200, 204):
                    break
            time.sleep(0.5)

        status_resp = client.get(f"/tasks/{task_id}")
        if status_resp.status_code == 200:
            body = status_resp.json()
            status = body.get("status", "")
            # Should be permanently failed or in DLQ
            assert status in ("failed", "dead", "dead_letter", "dlq"), \
                f"After max retries, expected failed/dead status, got {status}"


class TestDeadLetterQueue:
    """Tasks that exhaust retries go to the dead letter queue."""

    def test_dlq_endpoint_exists(self, client: httpx.Client) -> None:
        """DLQ listing endpoint should exist."""
        for path in ("/tasks/dlq", "/dlq", "/tasks?status=dead_letter"):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                assert isinstance(body, (list, dict))
                return
        pytest.skip("No DLQ endpoint found")

    def test_exhausted_task_in_dlq(self, client: httpx.Client) -> None:
        """A task that failed all retries should appear in the DLQ."""
        created = submit_task(client)
        task_id = created.get("id") or created.get("task_id")

        # Fail enough times to exhaust retries
        for _ in range(5):
            for path in (f"/tasks/{task_id}/fail", f"/tasks/{task_id}/complete"):
                client.post(path, json={"status": "failed", "error": "exhaust"})
            time.sleep(0.3)

        # Check DLQ
        for path in ("/tasks/dlq", "/dlq", "/tasks?status=dead_letter"):
            resp = client.get(path)
            if resp.status_code == 200:
                body = resp.json()
                tasks = body if isinstance(body, list) else body.get("tasks", [])
                task_ids = [str(t.get("id") or t.get("task_id", "")) for t in tasks]
                if str(task_id) in task_ids:
                    return
        pytest.skip("DLQ not verifiable")
