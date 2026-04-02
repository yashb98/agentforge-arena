"""Tests for L2 Module Memory models."""

from __future__ import annotations

from uuid import uuid4

from packages.memory.src.module.models import ModuleRecord, RecordType
from packages.shared.src.types.models import AgentRole


class TestRecordType:
    def test_all_10_record_types_exist(self) -> None:
        assert len(RecordType) == 10

    def test_record_type_values_are_snake_case(self) -> None:
        for rt in RecordType:
            assert rt.value == rt.value.lower()
            assert " " not in rt.value


class TestModuleRecord:
    def test_create_adr_record(self) -> None:
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.ADR,
            module_name="auth",
            title="Chose bcrypt over argon2",
            content="bcrypt — simpler API, well-supported.",
        )
        assert record.record_type == RecordType.ADR
        assert record.synced_to_docs is False
        assert record.id is not None

    def test_create_gotcha_record(self) -> None:
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.GOTCHA,
            module_name="cache",
            title="Redis drops idle connections",
            content="Wrap all Redis calls with tenacity retry.",
            agent_role=AgentRole.BUILDER,
        )
        assert record.record_type == RecordType.GOTCHA
        assert record.agent_role == AgentRole.BUILDER

    def test_serialization_roundtrip(self) -> None:
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.CODING_PATTERN,
            module_name="api",
            title="Use Depends() for DI",
            content="Always use FastAPI Depends() for dependency injection.",
        )
        json_str = record.model_dump_json()
        restored = ModuleRecord.model_validate_json(json_str)
        assert restored.id == record.id
        assert restored.record_type == RecordType.CODING_PATTERN

    def test_metadata_defaults_to_empty_dict(self) -> None:
        record = ModuleRecord(
            team_id=uuid4(),
            tournament_id=uuid4(),
            record_type=RecordType.FILE_META,
            module_name="main",
            title="Entry point",
            content="FastAPI app factory.",
        )
        assert record.metadata == {}
