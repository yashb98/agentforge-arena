---
name: project-scaffolder
description: |
  Scaffold a complete, production-ready project structure from a challenge brief.
  Use this skill whenever an agent needs to create a new project from scratch,
  set up a codebase skeleton, or initialize a project with CLAUDE.md, rules,
  hooks, and proper directory structure. Triggers on: "create project",
  "scaffold", "initialize", "set up new project", "bootstrap project",
  or when the Architect agent begins the ARCHITECTURE phase.
---

# Project Scaffolder Skill

## Purpose
Transform a challenge brief into a complete project skeleton that agents can
immediately start building in. This is the Architect agent's primary tool.

## Scope boundary (Arena tournaments)

Scaffold and refine **only inside the team’s challenge repository** — the `project/` directory rooted at that team’s sandbox workspace (`…/team-{id}/project/`). All later edits to rules, hooks, skills, ADRs, architecture docs, and specs belong there.

Do **not** modify the AgentForge Arena monorepo (`packages/`, platform `.claude/`, etc.) when executing a challenge; that is outside the competition workspace.

## Workflow

### Step 1: Analyze the Challenge Brief
Read the challenge and extract:
- **Core functionality** — What does the app need to DO?
- **Tech stack hints** — Does the challenge specify/prefer certain technologies?
- **Scale requirements** — Single user? Multi-tenant? Real-time?
- **Data model** — What entities exist? What are the relationships?
- **API surface** — What endpoints are needed?
- **UI requirements** — What pages/views are needed?

### Step 2: Choose the Stack
Based on analysis, select from proven templates:

| Challenge Type | Backend | Frontend | Database | Extra |
|---------------|---------|----------|----------|-------|
| SaaS App | FastAPI | Next.js 15 | PostgreSQL | Redis, S3 |
| CLI Tool | Python + Click | — | SQLite | — |
| API Service | FastAPI | — | PostgreSQL | Redis |
| AI Agent | LangGraph + FastAPI | Next.js 15 | PostgreSQL + Qdrant | LangFuse |
| Real-time App | FastAPI + WebSocket | Next.js 15 | PostgreSQL | Redis Pub/Sub |

### Step 3: Generate Project Structure
```
project/
├── CLAUDE.md                    ← Project context for all agents
├── ARCHITECTURE.md              ← System design document
├── RESEARCH.md                  ← Research findings (from Researcher agent)
├── README.md                    ← Project documentation
├── .claude/
│   ├── rules/
│   │   └── project-rules.md    ← Stack-specific coding standards
│   ├── hooks/
│   │   └── post-write.sh       ← Auto-format on save
│   └── skills/                  ← Bundled packs seeded by Arena + custom skills
├── pyproject.toml               ← Python dependencies + config
├── src/
│   ├── __init__.py
│   ├── main.py                  ← FastAPI app entry point
│   ├── config.py                ← Pydantic Settings
│   ├── models/                  ← Pydantic + SQLAlchemy models
│   │   ├── __init__.py
│   │   └── base.py
│   ├── api/                     ← FastAPI routers
│   │   ├── __init__.py
│   │   ├── router.py
│   │   └── deps.py
│   ├── services/                ← Business logic
│   │   └── __init__.py
│   ├── repositories/            ← Database access
│   │   └── __init__.py
│   └── utils/                   ← Shared utilities
│       └── __init__.py
├── tests/
│   ├── conftest.py
│   ├── factories.py
│   └── unit/
│       └── __init__.py
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

### Step 4: Generate the Project's CLAUDE.md
Every scaffolded project gets its own CLAUDE.md:

```markdown
# [Project Name] — CLAUDE.md

## What This Project Is
[One paragraph from challenge brief]

## Tech Stack
- Backend: [chosen stack]
- Database: [chosen DB]
- Frontend: [if applicable]

## Architecture
See ARCHITECTURE.md for full system design.

## Key Files
- `src/main.py` — Application entry point
- `src/config.py` — All configuration via environment variables
- `src/models/` — Data models (Pydantic + SQLAlchemy)
- `src/api/` — API endpoints
- `src/services/` — Business logic layer

## Agent Task Assignments
- **Builder**: `src/models/`, `src/services/`, `src/repositories/`
- **Frontend**: `frontend/` (if applicable)
- **Tester**: `tests/`
- **Critic**: Reviews everything

## Coding Standards
See `.claude/rules/project-rules.md`

## Running Locally
```bash
pip install -e .
uvicorn src.main:app --reload
pytest
```
```

### Step 5: Generate Starter Files
Create minimal but RUNNABLE starter files so agents can immediately test:
- `main.py` with a health check endpoint
- `config.py` with Pydantic Settings
- `conftest.py` with basic fixtures
- `Dockerfile` with multi-stage build
- `.env.example` with all required variables
