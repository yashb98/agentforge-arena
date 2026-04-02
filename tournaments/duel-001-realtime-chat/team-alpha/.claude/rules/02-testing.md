# Testing Rules
- pytest + pytest-asyncio for all tests
- Test naming: test_<what>_<when>_<expected>
- Fixtures in conftest.py, never inline setup
- Mock at boundaries only (DB, external services)
- Min 80% coverage target
