# Rule 03: Testing Standards

## Applies To
All packages in `packages/`.

## Coverage Requirements
| Package | Minimum Coverage | Rationale |
|---------|-----------------|-----------|
| `shared` | 90% | Foundation for everything |
| `core` | 85% | Tournament logic must be correct |
| `sandbox` | 80% | Security-critical paths tested |
| `agents` | 80% | Agent lifecycle correctness |
| `judge` | 95% | Judging must be deterministic and fair |
| `spectator` | 70% | UI-adjacent, some manual testing acceptable |
| `api` | 85% | All endpoints tested |
| `web` | 60% | Component tests + E2E for critical flows |
| `replay` | 80% | Data integrity matters |
| `research` | 70% | External APIs are mocked |

## Python Testing Stack
- **Framework**: pytest with pytest-asyncio
- **Coverage**: coverage.py with branch coverage
- **Mocking**: pytest-mock (unittest.mock under the hood)
- **Fixtures**: Shared fixtures in `conftest.py` per package
- **Factory**: factory_boy for model factories
- **Database**: pytest-postgresql for real DB tests (not SQLite)
- **Redis**: fakeredis for unit tests, real Redis for integration

## Test Organization
```
packages/<name>/tests/
├── conftest.py          ← Shared fixtures
├── factories.py         ← Model factories
├── unit/                ← Fast, isolated, mocked dependencies
│   ├── test_models.py
│   └── test_services.py
├── integration/         ← Real DB, real Redis, real Docker
│   ├── test_api.py
│   └── test_workflows.py
└── e2e/                 ← Full system tests (run in CI only)
    └── test_tournament_flow.py
```

## Test Naming Convention
```python
def test_<what>_<when>_<expected>():
    """Example: test_tournament_start_with_valid_config_creates_sandboxes"""

# Good:
def test_elo_update_after_match_adjusts_both_teams():
def test_sandbox_create_with_exceeded_memory_raises_resource_error():
def test_judge_score_with_failing_tests_returns_zero_functionality():

# Bad:
def test_tournament():          # Too vague
def test_it_works():            # Meaningless
def test_sandbox_1():           # Not descriptive
```

## What Must Be Tested
1. **Happy path** — Normal operation produces correct result
2. **Error paths** — Invalid input, missing data, network failures
3. **Edge cases** — Empty lists, zero values, max limits, Unicode
4. **Concurrency** — Race conditions in async operations
5. **Security boundaries** — Sandbox escapes, injection, privilege escalation
6. **Idempotency** — Same operation twice produces same result

## Mocking Rules
- Mock at the boundary (HTTP clients, Docker SDK, LLM providers)
- NEVER mock the thing you're testing
- Use dependency injection to make mocking easy
- Integration tests should use real services (DB, Redis) via Docker Compose
- LLM responses: Use recorded fixtures (VCR-style) for determinism

## CI Pipeline
```yaml
# Runs on every PR
- ruff check .
- mypy --strict packages/
- pytest packages/ --cov --cov-branch --cov-fail-under=80
- eslint packages/web/
- tsc --noEmit packages/web/
- jest packages/web/ --coverage
```
