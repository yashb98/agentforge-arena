"""Tests for L3 Semantic Memory models."""

from __future__ import annotations

from uuid import uuid4

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.memory.src.semantic.models import CodeChunk, MemoryContext, SearchResult
from packages.memory.src.working.models import WorkingState
from packages.shared.src.types.models import AgentRole, TournamentPhase


class TestCodeChunk:
    def test_create_function_chunk(self) -> None:
        chunk = CodeChunk(
            chunk_id="src/auth.py::login",
            file_path="src/auth.py",
            language="python",
            module_name="auth",
            symbol_name="login",
            symbol_type="function",
            content="def login(username: str, password: str) -> Token:\n    ...",
            line_start=10,
            line_end=25,
        )
        assert chunk.symbol_type == "function"
        assert chunk.dependencies == []

    def test_chunk_id_format(self) -> None:
        chunk = CodeChunk(
            chunk_id="src/models.py::User",
            file_path="src/models.py",
            language="python",
            module_name="models",
            symbol_name="User",
            symbol_type="class",
            content="class User(BaseModel): ...",
            line_start=1,
            line_end=20,
        )
        assert "::" in chunk.chunk_id


class TestSearchResult:
    def test_semantic_search_result(self) -> None:
        chunk = CodeChunk(
            chunk_id="src/auth.py::login",
            file_path="src/auth.py",
            language="python",
            module_name="auth",
            content="def login(): ...",
            line_start=1,
            line_end=5,
        )
        result = SearchResult(
            source="semantic",
            score=0.92,
            chunk=chunk,
            snippet="src/auth.py:1-5 login()",
        )
        assert result.source == "semantic"
        assert result.record is None

    def test_module_search_result(self) -> None:
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt",
            content="bcrypt for password hashing.",
        )
        result = SearchResult(
            source="module",
            score=0.85,
            record=record,
            snippet="ADR: Chose bcrypt for password hashing.",
        )
        assert result.source == "module"
        assert result.chunk is None


class TestMemoryContext:
    def test_format_for_prompt_returns_string(self) -> None:
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
            current_task="Build auth",
        )
        ctx = MemoryContext(
            working_state=state,
            module_context=[],
            semantic_context=[],
            total_tokens_estimate=500,
        )
        prompt = ctx.format_for_prompt()
        assert isinstance(prompt, str)
        assert "Build auth" in prompt

    def test_total_tokens_reflects_all_layers(self) -> None:
        state = WorkingState(
            agent_id=uuid4(),
            team_id=uuid4(),
            role=AgentRole.BUILDER,
            current_phase=TournamentPhase.BUILD,
        )
        ctx = MemoryContext(
            working_state=state,
            module_context=[],
            semantic_context=[],
            total_tokens_estimate=1234,
        )
        assert ctx.total_tokens_estimate == 1234
