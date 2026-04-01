# Plan 3: Challenge Library

> Full spec — creates the challenge library with starter challenges, hidden test suites, wires orchestrator loading, and connects the challenge route module.

## Problem Statement

Three disconnected pieces:
1. `orchestrator._select_random_challenge()` returns hardcoded `"url-shortener-saas"` (line 510)
2. `orchestrator._load_challenge()` returns a generic placeholder string (line 515)
3. `challenges.py` routes already parse `CHALLENGE.md` files from `challenges/library/` — but the directory may only have one challenge with no hidden tests

The judge's `_judge_match()` references `challenges/library/{challenge_id}/hidden_tests` — these don't exist yet.

## Architecture

```
challenges/
├── library/
│   ├── url-shortener-saas/
│   │   ├── CHALLENGE.md          ← Brief shown to teams
│   │   ├── hidden_tests/
│   │   │   ├── conftest.py       ← Shared fixtures for hidden tests
│   │   │   ├── test_api.py       ← API endpoint tests
│   │   │   ├── test_redirect.py  ← Redirect functionality tests
│   │   │   └── test_analytics.py ← Analytics feature tests
│   │   └── scoring_config.json   ← Optional weight overrides
│   ├── realtime-chat-app/
│   │   ├── CHALLENGE.md
│   │   ├── hidden_tests/
│   │   │   ├── conftest.py
│   │   │   ├── test_websocket.py
│   │   │   ├── test_rooms.py
│   │   │   └── test_persistence.py
│   │   └── scoring_config.json
│   └── task-queue-engine/
│       ├── CHALLENGE.md
│       ├── hidden_tests/
│       │   ├── conftest.py
│       │   ├── test_queue.py
│       │   ├── test_workers.py
│       │   └── test_retry.py
│       └── scoring_config.json
└── README.md                      ← How to write challenges
```

## Changes Required

### Step 1: Create Challenge 1 — `url-shortener-saas`

This challenge likely already has a `CHALLENGE.md`. We need to verify/improve it and add hidden tests.

**CHALLENGE.md** format (matches what `challenges.py` parser expects):

```markdown
# Challenge: URL Shortener SaaS

## Difficulty: Medium | Category: SaaS App | Time: 90 minutes

## Brief

Build a production-ready URL shortener service with analytics.
Users can create short URLs, get redirected, and view click analytics.
The service should handle high throughput and provide a clean API.

## Requirements

1. **Create Short URL** — POST endpoint accepting a long URL, returns a short code
2. **Redirect** — GET /{code} redirects to the original URL with 301/302
3. **Analytics** — GET endpoint returning click count, referrer, timestamp per short URL
4. **Custom Aliases** — Optional custom short codes with conflict detection
5. **Expiration** — URLs can have optional TTL, expired URLs return 410 Gone
6. **Rate Limiting** — Basic rate limiting on creation endpoint
7. **Health Check** — GET /health endpoint

## Technical Constraints

- Must use Python (FastAPI or Flask) OR Node.js (Express or Fastify)
- Must include a test suite with >60% coverage
- Must include a README with setup instructions
- Must include an ARCHITECTURE.md explaining design decisions

## Hints About Hidden Tests

- The hidden test suite will call your API endpoints directly
- Tests check both happy paths and edge cases (invalid URLs, duplicate aliases, expired URLs)
- Performance test: 100 URLs created in sequence must complete in <10 seconds
- The test suite expects your app to run on port 8000
```

**hidden_tests/conftest.py:**
```python
"""Shared fixtures for URL Shortener hidden tests."""
import httpx
import pytest

BASE_URL = "http://localhost:8000"

@pytest.fixture
def client():
    return httpx.Client(base_url=BASE_URL, timeout=10.0)

@pytest.fixture
def async_client():
    return httpx.AsyncClient(base_url=BASE_URL, timeout=10.0)
```

**hidden_tests/test_api.py** — Tests for create, redirect, analytics, custom aliases, expiration, rate limiting, health check. ~15-20 test cases.

**hidden_tests/test_redirect.py** — Tests for redirect behavior, 301 vs 302, expired URLs returning 410, non-existent codes returning 404.

**hidden_tests/test_analytics.py** — Tests for click counting, referrer tracking, time-series data.

### Step 2: Create Challenge 2 — `realtime-chat-app`

**CHALLENGE.md:**
```markdown
# Challenge: Real-Time Chat Application

## Difficulty: Hard | Category: Real Time | Time: 120 minutes

## Brief

Build a real-time chat application with rooms, message persistence, and user presence.

## Requirements

1. **WebSocket Connection** — Clients connect via WebSocket with authentication
2. **Chat Rooms** — Create, join, leave rooms. List active rooms.
3. **Message Sending** — Send messages to rooms, receive in real-time
4. **Message History** — Retrieve past messages with pagination
5. **User Presence** — Show who's online in each room
6. **Typing Indicators** — Broadcast when a user is typing
7. **Message Search** — Search messages by keyword within a room
```

**hidden_tests/** — WebSocket connection tests, room CRUD, message delivery, persistence, presence, search.

### Step 3: Create Challenge 3 — `task-queue-engine`

**CHALLENGE.md:**
```markdown
# Challenge: Distributed Task Queue Engine

## Difficulty: Hard | Category: API Service | Time: 120 minutes

## Brief

Build a task queue system where clients submit jobs, workers process them, and results are retrievable.

## Requirements

1. **Submit Task** — POST endpoint to enqueue a task with payload
2. **Task Status** — GET endpoint to check task status (pending/running/completed/failed)
3. **Task Result** — GET endpoint to retrieve completed task results
4. **Worker Registration** — Workers register and poll for tasks
5. **Retry Logic** — Failed tasks retry up to 3 times with exponential backoff
6. **Priority Queues** — Tasks can have priority levels (high/normal/low)
7. **Dead Letter Queue** — Tasks that fail all retries go to DLQ
```

**hidden_tests/** — Task submission, status tracking, worker polling, retry behavior, priority ordering, DLQ tests.

### Step 4: Wire `_load_challenge()` in orchestrator

Replace the TODO with filesystem-based loading (same pattern as `challenges.py` routes):

```python
async def _load_challenge(self, challenge_id: str) -> str:
    """Load challenge brief markdown from the library."""
    from pathlib import Path

    # challenges/library/{id}/CHALLENGE.md
    repo_root = Path(__file__).resolve().parents[4]
    challenge_file = repo_root / "challenges" / "library" / challenge_id / "CHALLENGE.md"

    if not challenge_file.is_file():
        logger.error("Challenge file not found: %s", challenge_file)
        return f"# Challenge: {challenge_id}\n\nChallenge brief not found."

    return challenge_file.read_text(encoding="utf-8")
```

### Step 5: Wire `_select_random_challenge()` in orchestrator

```python
async def _select_random_challenge(self) -> str:
    """Select a random challenge from the library."""
    import random
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[4]
    library_dir = repo_root / "challenges" / "library"

    if not library_dir.is_dir():
        logger.warning("Challenge library not found at %s", library_dir)
        return "url-shortener-saas"  # Fallback

    challenges = [
        d.name for d in library_dir.iterdir()
        if d.is_dir() and (d / "CHALLENGE.md").is_file()
    ]

    if not challenges:
        return "url-shortener-saas"

    selected = random.choice(challenges)
    logger.info("Selected random challenge: %s", selected)
    return selected
```

### Step 6: Create `scoring_config.json` per challenge

Optional weight overrides for judge dimensions:

```json
{
  "scoring_weights": {
    "functionality": 0.35,
    "code_quality": 0.20,
    "test_coverage": 0.15,
    "ux_design": 0.10,
    "architecture": 0.10,
    "innovation": 0.10
  },
  "hidden_test_timeout_seconds": 120,
  "expected_port": 8000
}
```

The `JudgeService` can load this to customize scoring per challenge.

### Step 7: Wire hidden tests path in JudgeService

Update `_judge_match()` to resolve the hidden tests path correctly:

```python
async def _judge_match(self, tournament_id, team_a_id, team_b_id, challenge_id):
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[4]
    hidden_tests = str(repo_root / "challenges" / "library" / challenge_id / "hidden_tests")

    # Verify hidden tests exist
    if not Path(hidden_tests).is_dir():
        logger.error("Hidden tests not found for challenge %s", challenge_id)
        # Fall back to team's own tests
        hidden_tests = None

    # ... rest of judging logic
```

## Files Created

| File | Purpose |
|------|---------|
| `challenges/library/url-shortener-saas/CHALLENGE.md` | Challenge brief (verify/update existing) |
| `challenges/library/url-shortener-saas/hidden_tests/conftest.py` | Shared test fixtures |
| `challenges/library/url-shortener-saas/hidden_tests/test_api.py` | API endpoint tests |
| `challenges/library/url-shortener-saas/hidden_tests/test_redirect.py` | Redirect tests |
| `challenges/library/url-shortener-saas/hidden_tests/test_analytics.py` | Analytics tests |
| `challenges/library/url-shortener-saas/scoring_config.json` | Score weight overrides |
| `challenges/library/realtime-chat-app/CHALLENGE.md` | Challenge brief |
| `challenges/library/realtime-chat-app/hidden_tests/` | 3-4 test files |
| `challenges/library/realtime-chat-app/scoring_config.json` | Score weight overrides |
| `challenges/library/task-queue-engine/CHALLENGE.md` | Challenge brief |
| `challenges/library/task-queue-engine/hidden_tests/` | 3-4 test files |
| `challenges/library/task-queue-engine/scoring_config.json` | Score weight overrides |
| `challenges/README.md` | How to write new challenges |

## Files Modified

| File | Change |
|------|--------|
| `packages/core/src/tournament/orchestrator.py` | Wire `_load_challenge()` and `_select_random_challenge()` |
| `packages/judge/src/scoring/service.py` | Resolve hidden tests path, load scoring config |

## Dependencies

- **Independent of Plans 1-2** — challenges are filesystem-based, no service wiring needed
- Hidden tests use `httpx` to call the team's running app — this is already a dev dependency

## Testing Strategy

1. **Test challenge parsing** — verify `_parse_challenge_md()` works for all 3 challenges
2. **Test challenge selection** — verify `_select_random_challenge()` picks from available
3. **Test challenge loading** — verify `_load_challenge()` reads correct file
4. **Test hidden tests independently** — each hidden test suite should run against a mock server
5. **Test scoring config loading** — verify weight overrides are applied

### Test files:
- `packages/core/tests/test_challenge_loading.py`
- `challenges/library/url-shortener-saas/hidden_tests/` (are themselves tests)

## Acceptance Criteria

- [ ] 3 challenges exist in `challenges/library/` with CHALLENGE.md + hidden_tests/
- [ ] Each challenge has 10+ hidden test cases covering happy path + edge cases
- [ ] `GET /api/v1/challenges` returns all 3 challenges with correct metadata
- [ ] `GET /api/v1/challenges/{id}` returns challenge details or 404
- [ ] `_select_random_challenge()` picks from available challenges randomly
- [ ] `_load_challenge()` returns the full CHALLENGE.md content
- [ ] Hidden tests use httpx to call team's app (no internal imports)
- [ ] Each challenge has a `scoring_config.json` with weight overrides
- [ ] `JudgeService` resolves hidden tests path correctly per challenge
