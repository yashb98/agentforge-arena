# Challenge: Distributed Task Queue Engine

## Difficulty: Hard | Category: API Service | Time: 120 minutes

## Brief

Build a task queue system where clients submit jobs, workers process them,
and results are retrievable. The system should handle failures gracefully
with retries, priority ordering, and a dead letter queue.

## Requirements

### Functional (Must Have)
1. **Submit Task** — POST endpoint to enqueue a task with JSON payload and optional priority
2. **Task Status** — GET endpoint returning task status (pending/running/completed/failed)
3. **Task Result** — GET endpoint to retrieve the completed task's result
4. **Worker Registration** — Workers register via POST and poll for tasks to execute
5. **Retry Logic** — Failed tasks retry up to 3 times with exponential backoff
6. **Priority Queues** — Tasks with higher priority are dequeued first (high > normal > low)

### Non-Functional (Should Have)
7. **Dead Letter Queue** — Tasks that exhaust retries move to DLQ; DLQ is listable
8. **Task Cancellation** — Cancel a pending task before it's picked up
9. **Worker Heartbeat** — Workers send heartbeats; stuck tasks are re-queued after timeout
10. **Batch Submit** — Submit multiple tasks in a single request

### Bonus (Nice to Have)
11. **Task Dependencies** — Task B waits for Task A to complete
12. **Scheduled Tasks** — Submit a task to run at a future time
13. **Metrics Dashboard** — Endpoint returning queue depth, throughput, avg latency

## Tech Constraints
- Backend: Python (FastAPI preferred) or Node.js (Express/Fastify)
- Persistence: Any (PostgreSQL, SQLite, Redis)
- Must include a Dockerfile
- Must include a README with setup instructions
- Must include an ARCHITECTURE.md

## Hidden Test Suite Hints
- Tests submit tasks and poll for completion
- Tests verify priority ordering by submitting mixed-priority tasks
- Tests intentionally fail tasks to verify retry + DLQ behavior
- Tests register mock workers and verify task assignment
- Tests check status transitions: pending → running → completed/failed
- The test suite expects your app to run on port 8000

## Scoring Weights
| Dimension | Weight |
|-----------|--------|
| Functionality | 0.35 |
| Code Quality | 0.20 |
| Test Coverage | 0.15 |
| UX/Design | 0.05 |
| Architecture | 0.15 |
| Innovation | 0.10 |
