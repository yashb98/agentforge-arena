# Rule 01: Code Quality Standards

## Applies To
All source code in `packages/`.

## Python Quality Gates
- **Linter**: `ruff check --select=ALL --ignore=D100,D104` — zero warnings
- **Formatter**: `ruff format` — enforced via pre-commit hook
- **Type checker**: `mypy --strict` — zero errors (use `type: ignore[code]` with justification comment ONLY)
- **Complexity**: Max cyclomatic complexity 15 per function. Extract if higher.
- **Function length**: Max 50 lines. Extract helper functions.
- **File length**: Max 500 lines. Split into modules.
- **No `Any` types** unless documented with `# REASON: <why Any is necessary>`

## TypeScript Quality Gates
- **Linter**: `eslint --max-warnings=0`
- **Formatter**: `prettier --check`
- **Type checker**: `tsc --noEmit --strict`
- **No `any` types** — use `unknown` and narrow, or define proper types
- **No `@ts-ignore`** — use `@ts-expect-error` with explanation

## Pydantic Models (Python)
- ALL data structures are Pydantic v2 `BaseModel`
- Use `model_validator` for cross-field validation
- Use `Field(description=...)` for all fields
- Use `ConfigDict(strict=True)` for models crossing trust boundaries (API input, agent messages)
- Serialize with `.model_dump(mode="json")`, never raw dict access

## React Components (TypeScript)
- Functional components only, no class components
- Props defined as TypeScript interfaces, not inline
- Use `React.memo()` for expensive components
- Custom hooks for shared logic (in `packages/web/src/hooks/`)
- Server Components by default, `'use client'` only when needed

## Dependency Rules
- `packages/shared` has ZERO imports from other packages
- `packages/api` may import from `packages/core`, `packages/judge`, `packages/spectator`, `packages/shared`
- `packages/web` may import from `packages/shared` (types only)
- `packages/core` may import from `packages/shared`, `packages/sandbox`, `packages/agents`
- NO circular dependencies. If detected, extract to `packages/shared`

## Code Review Checklist (Critic Agent)
1. Does it compile/lint with zero warnings?
2. Are all public functions typed and documented?
3. Are error cases handled explicitly?
4. Is there test coverage for happy path AND error paths?
5. Are there hardcoded values that should be config?
6. Are there race conditions in async code?
7. Does it follow the naming conventions in Rule 00?
8. Is the function/file length within limits?
