"""SandboxManager tests with subprocess and settings mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from packages.sandbox.src.docker.manager import SandboxInfo, SandboxManager


def _proc(stdout: bytes = b"sbx-1\n", stderr: bytes = b"", rc: int = 0) -> AsyncMock:
    p = AsyncMock()
    p.communicate = AsyncMock(return_value=(stdout, stderr))
    p.returncode = rc
    return p


@pytest.fixture()
def fake_settings() -> MagicMock:
    s = MagicMock()
    s.sandbox.workspace_base = "/tmp/arena-sandbox-test"
    s.sandbox.network_allow = ["pypi.org"]
    return s


@pytest.mark.asyncio
async def test_create_sandbox_success_registers_info(
    monkeypatch: pytest.MonkeyPatch, fake_settings: MagicMock
) -> None:
    monkeypatch.setattr(
        "packages.sandbox.src.docker.manager.get_settings",
        lambda: fake_settings,
    )
    shell_proc = _proc()
    exec_proc = _proc()
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=shell_proc),
    ), patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=exec_proc),
    ):
        mgr = SandboxManager()
        sid = await mgr.create_sandbox("team-1", memory="2g", cpus=1)
    assert sid == "sbx-1"
    assert "team-1" in mgr._sandboxes
    info = mgr._sandboxes["team-1"]
    assert isinstance(info, SandboxInfo)
    assert info.memory == "2g"


@pytest.mark.asyncio
async def test_create_sandbox_failure_raises(
    monkeypatch: pytest.MonkeyPatch, fake_settings: MagicMock
) -> None:
    monkeypatch.setattr(
        "packages.sandbox.src.docker.manager.get_settings",
        lambda: fake_settings,
    )
    shell_proc = _proc(stdout=b"", stderr=b"docker exploded", rc=1)
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=shell_proc),
    ):
        mgr = SandboxManager()
        with pytest.raises(RuntimeError, match="Failed to create sandbox"):
            await mgr.create_sandbox("t2")


@pytest.mark.asyncio
async def test_write_read_file_requires_sandbox(
    monkeypatch: pytest.MonkeyPatch, fake_settings: MagicMock
) -> None:
    monkeypatch.setattr(
        "packages.sandbox.src.docker.manager.get_settings",
        lambda: fake_settings,
    )
    shell_proc = _proc()
    exec_proc = _proc()
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=shell_proc),
    ), patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=exec_proc),
    ):
        mgr = SandboxManager()
        await mgr.create_sandbox("w1")
    cat_proc = _proc(stdout=b"hello", rc=0)
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=cat_proc),
    ):
        text = await mgr.read_file("w1", "src/foo.txt")
    assert text == "hello"


@pytest.mark.asyncio
async def test_read_file_missing_team_raises() -> None:
    mgr = SandboxManager()
    with pytest.raises(ValueError, match="No sandbox found"):
        await mgr.read_file("nope", "x")


@pytest.mark.asyncio
async def test_grant_and_revoke_read_access(
    monkeypatch: pytest.MonkeyPatch, fake_settings: MagicMock
) -> None:
    monkeypatch.setattr(
        "packages.sandbox.src.docker.manager.get_settings",
        lambda: fake_settings,
    )
    shell_proc = _proc()
    exec_proc = _proc()
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=shell_proc),
    ), patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=exec_proc),
    ):
        mgr = SandboxManager()
        await mgr.create_sandbox("a")
        await mgr.create_sandbox("b")
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=exec_proc),
    ):
        await mgr.grant_read_access("a", "b")
        await mgr.revoke_read_access("a")


@pytest.mark.asyncio
async def test_get_resource_usage_json_and_fallback(
    monkeypatch: pytest.MonkeyPatch, fake_settings: MagicMock
) -> None:
    monkeypatch.setattr(
        "packages.sandbox.src.docker.manager.get_settings",
        lambda: fake_settings,
    )
    shell_proc = _proc()
    exec_proc = _proc()
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=shell_proc),
    ), patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=exec_proc),
    ):
        mgr = SandboxManager()
        await mgr.create_sandbox("ru1")
    stats_proc = _proc(stdout=b'{"cpu": 1}', rc=0)
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=stats_proc),
    ):
        data = await mgr.get_resource_usage("ru1")
    assert data["cpu"] == 1

    bad_proc = _proc(stdout=b"not-json", rc=0)
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=bad_proc),
    ):
        raw = await mgr.get_resource_usage("ru1")
    assert "raw" in raw

    fail_stats = _proc(stdout=b"", stderr=b"err", rc=1)
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=fail_stats),
    ):
        fallback = await mgr.get_resource_usage("ru1")
    assert fallback.get("status") == "running"


@pytest.mark.asyncio
async def test_write_file_creates_path(
    monkeypatch: pytest.MonkeyPatch, fake_settings: MagicMock
) -> None:
    monkeypatch.setattr(
        "packages.sandbox.src.docker.manager.get_settings",
        lambda: fake_settings,
    )
    shell_proc = _proc()
    exec_proc = _proc()
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=shell_proc),
    ), patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=exec_proc),
    ):
        mgr = SandboxManager()
        await mgr.create_sandbox("wf1")
    write_proc = _proc(rc=0)
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=write_proc),
    ):
        await mgr.write_file("wf1", "src/x.txt", "hi")


@pytest.mark.asyncio
async def test_read_file_not_found_raises(
    monkeypatch: pytest.MonkeyPatch, fake_settings: MagicMock
) -> None:
    monkeypatch.setattr(
        "packages.sandbox.src.docker.manager.get_settings",
        lambda: fake_settings,
    )
    shell_proc = _proc()
    exec_proc = _proc()
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=shell_proc),
    ), patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=exec_proc),
    ):
        mgr = SandboxManager()
        await mgr.create_sandbox("nf1")
    bad_cat = _proc(stdout=b"", stderr=b"enoent", rc=1)
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=bad_cat),
    ), pytest.raises(FileNotFoundError):
        await mgr.read_file("nf1", "missing.txt")


@pytest.mark.asyncio
async def test_destroy_sandbox_and_destroy_all(
    monkeypatch: pytest.MonkeyPatch, fake_settings: MagicMock
) -> None:
    monkeypatch.setattr(
        "packages.sandbox.src.docker.manager.get_settings",
        lambda: fake_settings,
    )
    shell_proc = _proc()
    exec_proc = _proc()
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=shell_proc),
    ), patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_exec",
        AsyncMock(return_value=exec_proc),
    ):
        mgr = SandboxManager()
        await mgr.create_sandbox("d1")
        await mgr.create_sandbox("d2")
    rm_proc = _proc()
    with patch(
        "packages.sandbox.src.docker.manager.asyncio.create_subprocess_shell",
        AsyncMock(return_value=rm_proc),
    ):
        await mgr.destroy_sandbox("d1")
        assert "d1" not in mgr._sandboxes
        await mgr.destroy_all()
    assert mgr._sandboxes == {}
