# Testing Rules — TDD Workflow
1. Write the test FIRST — it must fail (red)
2. Write minimal implementation — test passes (green)
3. Refactor — clean up while tests stay green
- Use pytest-asyncio with auto mode
- Fixtures manage DB lifecycle — each test gets fresh state
- WebSocket tests: use multiple clients to verify broadcast
