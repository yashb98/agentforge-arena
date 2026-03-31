# packages/judge — CLAUDE.md

## What This Package Is
Multi-dimensional judging system. Combines automated tests, static analysis,
and LLM evaluation to produce fair, reproducible tournament scores.

## Key Modules
- `src/scoring/service.py` — JudgeService: orchestrates full pipeline
- `src/automated/pytest_runner.py` — Run hidden test suites
- `src/automated/quality_scanner.py` — ruff + mypy scoring
- `src/automated/coverage_analyzer.py` — coverage.py integration
- `src/llm/ux_reviewer.py` — LLM-based UX/design evaluation
- `src/llm/architecture_reviewer.py` — LLM architecture review
- `src/llm/innovation_scorer.py` — LLM innovation assessment
- `src/cross_review/coordinator.py` — Cross-team review orchestration

## Scoring Weights
| Dimension | Weight | Judge Type |
|-----------|--------|-----------|
| Functionality | 30% | Automated (pytest) |
| Code Quality | 20% | Automated (ruff/mypy) + LLM |
| Test Coverage | 15% | Automated (coverage.py) |
| UX/Design | 15% | LLM (Opus 4.6) |
| Architecture | 10% | LLM (Opus 4.6) |
| Innovation | 10% | LLM (Opus 4.6) |

## CRITICAL: Judge accuracy target is >90% agreement with human evaluation.
- 95% test coverage required for THIS package
- All scoring functions must be deterministic (same input → same output)
- LLM judge uses temperature=0 for reproducibility

## Dependencies
- `packages/shared` — Types, events, config
- `packages/sandbox` — Access to team workspaces
