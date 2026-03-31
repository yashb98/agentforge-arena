# packages/research — CLAUDE.md

## What This Package Is
Real-time intelligence engine. Searches GitHub, arXiv, and the web for the
latest techniques, libraries, and best practices. Used by the Researcher agent
and the /research-sweep command.

## Key Modules
- `src/github/search.py` — GitHub API repo/code search
- `src/github/analyzer.py` — Repo quality evaluation
- `src/arxiv/search.py` — arXiv paper search and parsing
- `src/web/scraper.py` — General web search and content extraction
- `src/aggregator/sweep.py` — Full research sweep orchestrator
- `src/embeddings/indexer.py` — Qdrant vector indexing for research cache

## Core Principle
**NEVER rely on training knowledge for implementation details.**
Always search for the latest patterns. This module exists to give agents
a competitive edge by finding CURRENT information.

## Rate Limiting
- GitHub: 5000 req/hour with token, 60 without
- arXiv: Be nice (1 req/3s)
- Web: Respect robots.txt, 1 req/s per domain

## Dependencies
- `packages/shared` — Types, events, config
