# Rule 00: Global Standards

## Applies To
All files, all packages, all agents.

## Language & Runtime
- Python 3.12+ for all backend code
- TypeScript 5.5+ strict mode for all frontend code
- Node.js 22 LTS for frontend tooling
- PostgreSQL 16 for relational data
- Redis 7 for cache, pub/sub, and streams

## Import Order (Python)
1. stdlib
2. third-party (fastapi, pydantic, redis, etc.)
3. local packages (`from packages.shared...`)
4. relative imports

## Import Order (TypeScript)
1. React/Next.js
2. Third-party libraries
3. `@/components`
4. `@/lib`
5. `@/hooks`
6. `@/types`
7. Relative imports

## Naming Conventions
- Python: `snake_case` for functions/variables, `PascalCase` for classes, `SCREAMING_SNAKE` for constants
- TypeScript: `camelCase` for functions/variables, `PascalCase` for components/types, `SCREAMING_SNAKE` for constants
- Files: `snake_case.py` for Python, `kebab-case.tsx` for React components, `camelCase.ts` for utilities
- Database tables: `snake_case`, plural (`tournaments`, `agent_teams`, `match_results`)
- Redis keys: `namespace:entity:id` (e.g., `tournament:abc123:phase`)
- Events: `domain.entity.action` (e.g., `tournament.match.started`, `agent.task.completed`)

## Error Handling
- NEVER use bare `except:` — always catch specific exceptions
- ALWAYS include context in error messages: what failed, why, and what to do
- Use custom exception classes from `packages/shared/src/errors/`
- Log errors with structured logging (structlog)
- Propagate errors up with proper HTTP status codes in API layer

## Documentation
- Every public function/class gets a docstring
- Every module gets a module-level docstring
- Complex algorithms get inline comments explaining WHY, not WHAT
- ARCHITECTURE.md in every package root
- ADR (Architecture Decision Records) for non-obvious choices

## Git
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- Branch naming: `feat/description`, `fix/description`, `refactor/description`
- No commits directly to `main` — always PR
- Squash merge for feature branches

## Environment Variables
- NEVER hardcode secrets, API keys, or connection strings
- ALL config via environment variables with Pydantic Settings
- `.env.example` must be kept in sync with actual env vars
- Use `packages/shared/src/config.py` for centralized config
