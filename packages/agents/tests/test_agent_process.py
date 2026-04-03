"""
AgentForge Arena — Tests for AgentProcess with Redis Mailbox

Verifies that AgentProcess uses RedisMailbox for communication
instead of file-based JSON inboxes.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from packages.agents.src.teams.manager import AgentProcess, AgentTeamManager
from packages.shared.src.types.models import (
    Agent,
    AgentMessage,
    AgentRole,
    AgentStatus,
    MessageType,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture()
def mock_mailbox() -> MagicMock:
    """Create a mock RedisMailbox."""
    mailbox = MagicMock()
    mailbox.receive = AsyncMock(return_value=None)
    mailbox.receive_all = AsyncMock(return_value=[])
    mailbox.send = AsyncMock()
    mailbox.clear_team = AsyncMock()
    mailbox.clear_inbox = AsyncMock()
    return mailbox


@pytest.fixture()
def sample_agent() -> Agent:
    """Create a sample agent."""
    return Agent(
        id=uuid4(),
        team_id=uuid4(),
        tournament_id=uuid4(),
        role=AgentRole.BUILDER,
        model="claude-sonnet-4-6",
    )


@pytest.fixture()
def agent_process(sample_agent: Agent, mock_mailbox: MagicMock) -> AgentProcess:
    """Create an AgentProcess with mocked mailbox."""
    return AgentProcess(
        agent=sample_agent,
        system_prompt="You are a builder agent.",
        workspace_path="/tmp/test-workspace",
        mailbox=mock_mailbox,
        llm_client=None,
    )


@pytest.fixture()
def sample_message() -> AgentMessage:
    """Create a sample agent message."""
    return AgentMessage(
        id=uuid4(),
        from_agent=AgentRole.ARCHITECT,
        to_agent=AgentRole.BUILDER,
        message_type=MessageType.TASK_ASSIGNMENT,
        payload={"task": "Build the API"},
    )


# ============================================================
# AgentProcess Tests
# ============================================================


class TestAgentProcessMailbox:
    """Verify AgentProcess uses RedisMailbox, not file I/O."""

    def test_init_has_mailbox(self, agent_process: AgentProcess) -> None:
        """AgentProcess should have _mailbox, not inbox_path."""
        assert hasattr(agent_process, "_mailbox")
        assert not hasattr(agent_process, "inbox_path")

    @pytest.mark.asyncio
    async def test_read_inbox_calls_receive_all(
        self, agent_process: AgentProcess, mock_mailbox: MagicMock
    ) -> None:
        """_read_inbox() should delegate to RedisMailbox.receive_all()."""
        await agent_process._read_inbox()
        mock_mailbox.receive_all.assert_called_once_with(agent_process.agent.role)

    @pytest.mark.asyncio
    async def test_send_message_calls_mailbox_send(
        self, agent_process: AgentProcess, mock_mailbox: MagicMock, sample_message: AgentMessage
    ) -> None:
        """send_message() should delegate to RedisMailbox.send()."""
        await agent_process.send_message(sample_message)
        mock_mailbox.send.assert_called_once_with(sample_message)

    def test_no_mark_read_method(self, agent_process: AgentProcess) -> None:
        """_mark_read should not exist — RPOP is destructive."""
        assert not hasattr(agent_process, "_mark_read")

    @pytest.mark.asyncio
    async def test_process_message_increments_actions(
        self, agent_process: AgentProcess, sample_message: AgentMessage
    ) -> None:
        """Processing a message should increment actions_count."""
        await agent_process._process_message(sample_message)
        assert agent_process.agent.actions_count == 1

    @pytest.mark.asyncio
    async def test_process_message_calls_memory_hooks(
        self, sample_agent: Agent, mock_mailbox: MagicMock, sample_message: AgentMessage
    ) -> None:
        """When memory manager is configured, recall/record hooks should run."""
        llm_client = MagicMock()
        llm_client.completion = AsyncMock(
            return_value=SimpleNamespace(
                content="Implemented changes.",
                usage=SimpleNamespace(total_tokens=10, cost_usd=0.01),
            )
        )
        memory_manager = MagicMock()
        memory_manager.recall = AsyncMock(return_value={"l1": {"last_task": "x"}})
        memory_manager.record = AsyncMock()
        process = AgentProcess(
            agent=sample_agent,
            system_prompt="You are a builder agent.",
            workspace_path="/tmp/test-workspace",
            mailbox=mock_mailbox,
            llm_client=llm_client,
            memory_manager=memory_manager,
        )

        await process._process_message(sample_message)

        memory_manager.recall.assert_awaited_once()
        memory_manager.record.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_sets_active_status(self, agent_process: AgentProcess) -> None:
        """Starting the process sets status to ACTIVE."""
        await agent_process.start()
        assert agent_process.agent.status == AgentStatus.ACTIVE
        assert agent_process.agent.last_heartbeat is not None
        await agent_process.stop()

    @pytest.mark.asyncio
    async def test_stop_sets_terminated_status(self, agent_process: AgentProcess) -> None:
        """Stopping the process sets status to TERMINATED."""
        await agent_process.start()
        await agent_process.stop()
        assert agent_process.agent.status == AgentStatus.TERMINATED


# ============================================================
# AgentTeamManager Tests
# ============================================================


class TestAgentTeamManagerRedis:
    """Verify AgentTeamManager creates RedisMailbox per team."""

    def test_init_has_mailboxes_dict(self) -> None:
        """Manager should track mailboxes per team."""
        manager = AgentTeamManager(
            event_bus=MagicMock(),
            redis=MagicMock(),
            llm_client=None,
        )
        assert hasattr(manager, "_mailboxes")
        assert isinstance(manager._mailboxes, dict)

    def test_init_accepts_redis(self) -> None:
        """Manager constructor should accept redis parameter."""
        mock_redis = MagicMock()
        manager = AgentTeamManager(
            event_bus=MagicMock(),
            redis=mock_redis,
        )
        assert manager._redis is mock_redis

    @pytest.mark.asyncio
    async def test_teardown_team_clears_mailbox(self) -> None:
        """teardown_team should call clear_team() on the mailbox."""
        manager = AgentTeamManager(
            event_bus=MagicMock(),
            redis=MagicMock(),
        )

        team_id = uuid4()
        mock_mailbox = MagicMock()
        mock_mailbox.clear_team = AsyncMock()

        # Simulate having a team with a mailbox
        mock_process = MagicMock()
        mock_process.stop = AsyncMock()
        manager._teams[team_id] = [mock_process]
        manager._mailboxes[team_id] = mock_mailbox

        await manager.teardown_team(team_id)

        mock_mailbox.clear_team.assert_called_once()
        assert team_id not in manager._mailboxes
        assert team_id not in manager._teams

    @pytest.mark.asyncio
    async def test_teardown_all_clears_all_mailboxes(self) -> None:
        """teardown_all should clear all team mailboxes."""
        manager = AgentTeamManager(
            event_bus=MagicMock(),
            redis=MagicMock(),
        )

        for _ in range(3):
            team_id = uuid4()
            mock_mailbox = MagicMock()
            mock_mailbox.clear_team = AsyncMock()
            mock_process = MagicMock()
            mock_process.stop = AsyncMock()
            manager._teams[team_id] = [mock_process]
            manager._mailboxes[team_id] = mock_mailbox

        await manager.teardown_all()

        assert len(manager._teams) == 0
        assert len(manager._mailboxes) == 0

    @pytest.mark.asyncio
    async def test_spawn_team_without_redis_raises(self) -> None:
        """spawn_team should raise if Redis not configured."""
        manager = AgentTeamManager(
            event_bus=MagicMock(),
            redis=None,
        )
        with pytest.raises(RuntimeError, match="Redis not configured"):
            await manager.spawn_team(
                team_id=uuid4(),
                tournament_id=uuid4(),
                config=MagicMock(),
                sandbox_id="sandbox-1",
            )

    @pytest.mark.asyncio
    async def test_set_hierarchy_and_rollup_health(self) -> None:
        manager = AgentTeamManager(
            event_bus=MagicMock(),
            redis=MagicMock(),
        )
        tournament_id = uuid4()
        parent = uuid4()
        child = uuid4()
        manager._teams[child] = []  # no processes -> unhealthy team-not-found style payload
        await manager.set_team_hierarchy(
            tournament_id=tournament_id,
            hierarchy={parent: [child]},
        )

        summary = await manager.get_hierarchy_health(tournament_id)
        assert str(parent) in summary
        assert summary[str(parent)]["children"] == [str(child)]
