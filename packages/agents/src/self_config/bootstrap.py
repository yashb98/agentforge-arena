"""
AgentForge Arena — Agent Self-Configuration Bootstrap

This module enables agents to create their own project infrastructure:
- CLAUDE.md files for the projects they build
- .claude/rules/ for stack-specific coding standards
- .claude/hooks/ for auto-formatting
- .claude/skills/ for custom capabilities
- README.md, ARCHITECTURE.md, pyproject.toml, etc.

This is the "agents creating their own agent configs" capability.
The Architect agent uses this to bootstrap a complete project structure.
"""

from __future__ import annotations

import logging
from pathlib import Path
from textwrap import dedent

from packages.shared.src.types.models import ChallengeCategory

logger = logging.getLogger(__name__)


# Stack templates based on challenge category
STACK_TEMPLATES: dict[ChallengeCategory, dict[str, str]] = {
    ChallengeCategory.SAAS_APP: {
        "backend": "FastAPI",
        "frontend": "Next.js 15",
        "database": "PostgreSQL",
        "cache": "Redis",
        "orm": "SQLAlchemy 2.0",
    },
    ChallengeCategory.CLI_TOOL: {
        "backend": "Python + Click",
        "database": "SQLite",
    },
    ChallengeCategory.API_SERVICE: {
        "backend": "FastAPI",
        "database": "PostgreSQL",
        "cache": "Redis",
    },
    ChallengeCategory.AI_AGENT: {
        "backend": "FastAPI + LangGraph",
        "database": "PostgreSQL + Qdrant",
        "tracing": "Langfuse",
    },
    ChallengeCategory.REAL_TIME: {
        "backend": "FastAPI + WebSocket",
        "frontend": "Next.js 15",
        "database": "PostgreSQL",
        "cache": "Redis (Pub/Sub)",
    },
}


class ProjectBootstrapper:
    """Bootstraps a complete project structure for agent teams."""

    def __init__(self, workspace_path: str | Path) -> None:
        self.workspace = Path(workspace_path)

    async def bootstrap(
        self,
        challenge_title: str,
        challenge_description: str,
        category: ChallengeCategory,
        requirements: list[str],
        *,
        custom_stack: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Bootstrap a complete project structure.

        Returns a dict of created file paths → content summaries.
        """
        stack = custom_stack or STACK_TEMPLATES.get(category, STACK_TEMPLATES[ChallengeCategory.API_SERVICE])
        created_files: dict[str, str] = {}

        # 1. Project CLAUDE.md
        claude_md = self._generate_claude_md(challenge_title, challenge_description, stack, requirements)
        self._write(self.workspace / "CLAUDE.md", claude_md)
        created_files["CLAUDE.md"] = "Project context for all agents"

        # 2. ARCHITECTURE.md skeleton
        arch_md = self._generate_architecture_md(challenge_title, stack, requirements)
        self._write(self.workspace / "ARCHITECTURE.md", arch_md)
        created_files["ARCHITECTURE.md"] = "System design document"

        # 3. README.md
        readme = self._generate_readme(challenge_title, challenge_description, stack)
        self._write(self.workspace / "README.md", readme)
        created_files["README.md"] = "Project documentation"

        # 4. .claude/rules/project-rules.md
        rules = self._generate_rules(stack)
        self._write(self.workspace / ".claude" / "rules" / "project-rules.md", rules)
        created_files[".claude/rules/project-rules.md"] = "Stack-specific coding standards"

        # 5. .claude/hooks/post-write.sh
        hooks = self._generate_hooks(stack)
        self._write(self.workspace / ".claude" / "hooks" / "post-write.sh", hooks, executable=True)
        created_files[".claude/hooks/post-write.sh"] = "Auto-format hook"

        # 6. Python project files (if Python backend)
        if "FastAPI" in stack.get("backend", "") or "Python" in stack.get("backend", ""):
            self._bootstrap_python_project(stack, created_files)

        # 7. Config file
        config = self._generate_config(stack)
        self._write(self.workspace / "src" / "config.py", config)
        created_files["src/config.py"] = "Configuration via environment variables"

        # 8. Main entry point
        main = self._generate_main(stack)
        self._write(self.workspace / "src" / "main.py", main)
        created_files["src/main.py"] = "Application entry point"

        # 9. Test conftest
        conftest = self._generate_conftest()
        self._write(self.workspace / "tests" / "conftest.py", conftest)
        created_files["tests/conftest.py"] = "Test fixtures"

        # 10. Dockerfile
        dockerfile = self._generate_dockerfile(stack)
        self._write(self.workspace / "Dockerfile", dockerfile)
        created_files["Dockerfile"] = "Container definition"

        # 11. .env.example
        env = self._generate_env_example(stack)
        self._write(self.workspace / ".env.example", env)
        created_files[".env.example"] = "Environment variables template"

        logger.info("Bootstrapped %d files for project '%s'", len(created_files), challenge_title)
        return created_files

    # ========================================================
    # File Generators
    # ========================================================

    def _generate_claude_md(
        self, title: str, description: str, stack: dict, requirements: list[str]
    ) -> str:
        reqs = "\n".join(f"- {r}" for r in requirements)
        stack_lines = "\n".join(f"- **{k.title()}**: {v}" for k, v in stack.items())
        return dedent(f"""\
            # {title} — CLAUDE.md

            ## What This Project Is
            {description}

            ## Tech Stack
            {stack_lines}

            ## Requirements
            {reqs}

            ## Key Files
            - `src/main.py` — Application entry point
            - `src/config.py` — Configuration via environment variables
            - `src/models/` — Data models (Pydantic + ORM)
            - `src/api/` — API endpoints
            - `src/services/` — Business logic layer
            - `tests/` — Test suite

            ## Running
            ```bash
            pip install -e .
            uvicorn src.main:app --reload
            pytest
            ```
        """)

    def _generate_architecture_md(self, title: str, stack: dict, requirements: list[str]) -> str:
        return dedent(f"""\
            # {title} — Architecture

            ## System Overview
            [TODO: Architect fills in system diagram]

            ## Components
            [TODO: Architect defines component hierarchy]

            ## Data Models
            [TODO: Architect defines entity relationships]

            ## API Design
            [TODO: Architect defines endpoints]

            ## Stack Decisions
            {chr(10).join(f"- **{k}**: {v}" for k, v in stack.items())}

            ## Task Decomposition
            [TODO: Architect assigns tasks to Builder, Frontend, Tester]
        """)

    def _generate_readme(self, title: str, description: str, stack: dict) -> str:
        return dedent(f"""\
            # {title}

            {description}

            ## Quick Start
            ```bash
            pip install -e .
            cp .env.example .env
            uvicorn src.main:app --reload
            ```

            ## Testing
            ```bash
            pytest --cov
            ```

            ## Built by AgentForge Arena AI Agents
        """)

    def _generate_rules(self, stack: dict) -> str:
        rules = "# Project Coding Rules\n\n"
        if "FastAPI" in stack.get("backend", ""):
            rules += "- Use FastAPI for all endpoints\n"
            rules += "- Pydantic v2 models for all request/response shapes\n"
            rules += "- Async functions everywhere\n"
            rules += "- SQLAlchemy 2.0 async ORM for database access\n"
        if "Next.js" in stack.get("frontend", ""):
            rules += "- React Server Components by default\n"
            rules += "- TypeScript strict mode\n"
            rules += "- Tailwind CSS for styling\n"
        rules += "- Every function gets a docstring\n"
        rules += "- No bare except clauses\n"
        rules += "- Test coverage > 80%\n"
        return rules

    def _generate_hooks(self, stack: dict) -> str:
        return dedent("""\
            #!/usr/bin/env bash
            # Auto-format after file writes
            FILE="$1"
            EXT="${FILE##*.}"
            case "$EXT" in
                py) ruff format "$FILE" 2>/dev/null && ruff check --fix --select=I "$FILE" 2>/dev/null ;;
                ts|tsx|js|jsx) npx prettier --write "$FILE" 2>/dev/null ;;
            esac
        """)

    def _bootstrap_python_project(self, stack: dict, created_files: dict) -> None:
        """Create Python project structure."""
        dirs = [
            self.workspace / "src",
            self.workspace / "src" / "models",
            self.workspace / "src" / "api",
            self.workspace / "src" / "services",
            self.workspace / "src" / "repositories",
            self.workspace / "src" / "utils",
            self.workspace / "tests",
            self.workspace / "tests" / "unit",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            (d / "__init__.py").touch()
            created_files[f"{d.relative_to(self.workspace)}/__init__.py"] = "Package init"

        # pyproject.toml
        pyproject = dedent("""\
            [project]
            name = "arena-project"
            version = "0.1.0"
            requires-python = ">=3.12"
            dependencies = [
                "fastapi>=0.115.0",
                "uvicorn[standard]>=0.32.0",
                "pydantic>=2.10.0",
                "pydantic-settings>=2.6.0",
                "sqlalchemy[asyncio]>=2.0.36",
                "asyncpg>=0.30.0",
                "redis>=5.2.0",
                "httpx>=0.28.0",
            ]

            [project.optional-dependencies]
            dev = ["pytest>=8.3.0", "pytest-asyncio>=0.24.0", "pytest-cov>=6.0.0", "ruff>=0.8.0"]

            [tool.ruff]
            target-version = "py312"
            line-length = 100

            [tool.pytest.ini_options]
            asyncio_mode = "auto"
        """)
        self._write(self.workspace / "pyproject.toml", pyproject)
        created_files["pyproject.toml"] = "Python project config"

    def _generate_config(self, stack: dict) -> str:
        return dedent("""\
            \"\"\"Application configuration via environment variables.\"\"\"
            from pydantic_settings import BaseSettings

            class Settings(BaseSettings):
                app_name: str = "Arena Project"
                debug: bool = True
                database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/db"
                redis_url: str = "redis://localhost:6379/0"

                class Config:
                    env_file = ".env"

            settings = Settings()
        """)

    def _generate_main(self, stack: dict) -> str:
        return dedent("""\
            \"\"\"Application entry point.\"\"\"
            from fastapi import FastAPI
            from src.config import settings

            app = FastAPI(title=settings.app_name, debug=settings.debug)

            @app.get("/health")
            async def health():
                return {"status": "healthy", "app": settings.app_name}
        """)

    def _generate_conftest(self) -> str:
        return dedent("""\
            \"\"\"Test fixtures.\"\"\"
            import pytest
            from fastapi.testclient import TestClient
            from src.main import app

            @pytest.fixture
            def client():
                return TestClient(app)
        """)

    def _generate_dockerfile(self, stack: dict) -> str:
        return dedent("""\
            FROM python:3.12-slim AS base
            WORKDIR /app
            COPY pyproject.toml .
            RUN pip install --no-cache-dir .
            COPY . .
            CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
        """)

    def _generate_env_example(self, stack: dict) -> str:
        return dedent("""\
            APP_NAME=Arena Project
            DEBUG=true
            DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db
            REDIS_URL=redis://localhost:6379/0
        """)

    # ========================================================
    # Helpers
    # ========================================================

    def _write(self, path: Path, content: str, *, executable: bool = False) -> None:
        """Write a file, creating parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if executable:
            path.chmod(0o755)
