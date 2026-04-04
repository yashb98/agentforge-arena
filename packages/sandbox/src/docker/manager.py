"""
AgentForge Arena — Sandbox Manager

Manages Docker Sandbox MicroVM lifecycle for tournament teams.
Each team gets an isolated MicroVM with its own kernel, filesystem, and network.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from packages.sandbox.src.docker.team_skill_packs import seed_team_skill_packs
from packages.sandbox.src.docker.team_workspace_seed import (
    TEAM_PROJECT_CLAUDE_SETTINGS_JSON,
    TEAM_PROJECT_RULE_RESEARCH_FIRST,
    write_team_code_review_graph_seed,
)
from packages.shared.src.config import get_settings

logger = logging.getLogger(__name__)


def _write_team_claude_seed_files(project_root: Path) -> None:
    """Permissive Claude Code permissions + research-first rule (sandbox is the boundary)."""
    project_root.mkdir(parents=True, exist_ok=True)
    claude = project_root / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "settings.json").write_text(
        TEAM_PROJECT_CLAUDE_SETTINGS_JSON.strip() + "\n",
        encoding="utf-8",
    )
    rules = claude / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "00-research-before-implement.md").write_text(
        TEAM_PROJECT_RULE_RESEARCH_FIRST.strip() + "\n",
        encoding="utf-8",
    )


@dataclass
class SandboxInfo:
    """Metadata about a running sandbox."""

    team_id: str
    sandbox_id: str
    workspace_path: str
    memory: str
    cpus: int
    status: str = "running"
    network_allows: list[str] = field(default_factory=list)


class SandboxManager:
    """Manages Docker Sandbox MicroVM instances for tournament teams."""

    def __init__(self) -> None:
        self._sandboxes: dict[str, SandboxInfo] = {}

    def _memory_to_gib(self, memory: str) -> int:
        match = re.match(r"^(\d+)[gG]$", memory.strip())
        if not match:
            msg = f"Invalid memory format {memory!r}; expected '<n>g'"
            raise ValueError(msg)
        return int(match.group(1))

    async def create_sandbox(
        self,
        team_id: str,
        *,
        memory: str = "4g",
        cpus: int = 2,
    ) -> str:
        """Create an isolated Docker Sandbox MicroVM for a team.

        Returns the sandbox ID.
        """
        settings = get_settings()
        memory_gib = self._memory_to_gib(memory)
        if memory_gib > settings.sandbox.max_memory_gb:
            msg = (
                f"Requested memory {memory} exceeds sandbox cap "
                f"{settings.sandbox.max_memory_gb}g"
            )
            raise ValueError(msg)
        if cpus > settings.sandbox.max_cpus:
            msg = (
                f"Requested cpus {cpus} exceeds sandbox cap "
                f"{settings.sandbox.max_cpus}"
            )
            raise ValueError(msg)
        workspace = f"{settings.sandbox.workspace_base}/team-{team_id}"
        network_allows = settings.sandbox.network_allow

        # Build the docker sandbox create command
        allow_flags = " ".join(
            f"--network-allow {shlex.quote(domain)}" for domain in network_allows
        )

        cmd = (
            f"docker sandbox create claude {shlex.quote(workspace)} "
            f"{allow_flags} "
            f"--network-deny '*' "
            f"--memory {shlex.quote(memory)} "
            f"--cpus {cpus}"
        )

        logger.info("Creating sandbox for team %s: %s", team_id, cmd)

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error("Sandbox creation failed for team %s: %s", team_id, error_msg)
            raise RuntimeError(f"Failed to create sandbox: {error_msg}")

        sandbox_id = stdout.decode().strip() or f"sandbox-{team_id}"

        # Initialize the workspace structure
        await self._initialize_workspace(workspace, team_id)

        info = SandboxInfo(
            team_id=team_id,
            sandbox_id=sandbox_id,
            workspace_path=workspace,
            memory=memory,
            cpus=cpus,
            network_allows=network_allows,
        )
        self._sandboxes[team_id] = info

        logger.info("Sandbox created for team %s: %s", team_id, sandbox_id)
        return sandbox_id

    async def _initialize_workspace(self, workspace: str, team_id: str) -> None:
        """Set up the initial directory structure inside the sandbox."""
        dirs = [
            f"{workspace}/project",
            f"{workspace}/project/src",
            f"{workspace}/project/tests",
            f"{workspace}/project/.claude/rules",
            f"{workspace}/project/.claude/hooks",
            f"{workspace}/project/.claude/skills",
            f"{workspace}/inbox",
        ]

        for d in dirs:
            proc = await asyncio.create_subprocess_exec(
                "mkdir", "-p", d,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        # Initialize git repo
        proc = await asyncio.create_subprocess_exec(
            "git", "init", f"{workspace}/project",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Copy bundled skill packs (Hermes/agentskills-style dirs) into .claude/skills/
        await asyncio.to_thread(seed_team_skill_packs, Path(workspace) / "project")
        await asyncio.to_thread(_write_team_claude_seed_files, Path(workspace) / "project")
        await asyncio.to_thread(
            write_team_code_review_graph_seed,
            Path(workspace) / "project",
        )

    async def write_file(self, team_id: str, path: str, content: str) -> None:
        """Write a file into a team's sandbox workspace."""
        sandbox = self._sandboxes.get(team_id)
        if not sandbox:
            raise ValueError(f"No sandbox found for team {team_id}")

        full_path = f"{sandbox.workspace_path}/project/{path}"

        # Ensure parent directory exists
        parent = "/".join(full_path.split("/")[:-1])
        proc = await asyncio.create_subprocess_exec("mkdir", "-p", parent)
        await proc.communicate()

        # Write file
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", f"cat > {shlex.quote(full_path)}",
            stdin=asyncio.subprocess.PIPE,
        )
        await proc.communicate(input=content.encode())

    async def read_file(self, team_id: str, path: str) -> str:
        """Read a file from a team's sandbox workspace."""
        sandbox = self._sandboxes.get(team_id)
        if not sandbox:
            raise ValueError(f"No sandbox found for team {team_id}")

        full_path = f"{sandbox.workspace_path}/project/{path}"
        proc = await asyncio.create_subprocess_exec(
            "cat", full_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await proc.communicate()

        if proc.returncode != 0:
            raise FileNotFoundError(f"File not found: {path}")

        return stdout.decode()

    async def grant_read_access(self, reviewer_team: str, target_team: str) -> None:
        """Grant read-only access to another team's workspace (for cross-review)."""
        target = self._sandboxes.get(target_team)
        reviewer = self._sandboxes.get(reviewer_team)

        if not target or not reviewer:
            raise ValueError("One or both teams not found")

        # Create a read-only bind mount / symlink
        link_path = f"{reviewer.workspace_path}/opponent"
        proc = await asyncio.create_subprocess_exec(
            "ln", "-sfn", f"{target.workspace_path}/project", link_path,
        )
        await proc.communicate()

        logger.info("Granted read access: team %s can read team %s", reviewer_team, target_team)

    async def revoke_read_access(self, reviewer_team: str) -> None:
        """Revoke cross-review read access."""
        reviewer = self._sandboxes.get(reviewer_team)
        if reviewer:
            proc = await asyncio.create_subprocess_exec(
                "rm", "-f", f"{reviewer.workspace_path}/opponent",
            )
            await proc.communicate()

    async def get_resource_usage(self, team_id: str) -> dict:
        """Get resource usage stats for a sandbox."""
        sandbox = self._sandboxes.get(team_id)
        if not sandbox:
            return {"error": f"No sandbox for team {team_id}"}

        proc = await asyncio.create_subprocess_shell(
            f"docker sandbox stats {shlex.quote(sandbox.sandbox_id)} --no-stream --format json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode == 0:
            import json
            try:
                return json.loads(stdout.decode())
            except json.JSONDecodeError:
                return {"raw": stdout.decode()}

        return {"status": sandbox.status, "team_id": team_id}

    async def run_command(self, team_id: str, argv: list[str]) -> dict:
        """Run a command inside team project workspace."""
        sandbox = self._sandboxes.get(team_id)
        if not sandbox:
            raise ValueError(f"No sandbox found for team {team_id}")
        if not argv:
            raise ValueError("argv must contain at least one token")

        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=f"{sandbox.workspace_path}/project",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "returncode": int(proc.returncode),
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

    async def destroy_sandbox(self, team_id: str) -> None:
        """Destroy a team's sandbox and clean up resources."""
        sandbox = self._sandboxes.get(team_id)
        if not sandbox:
            logger.warning("No sandbox to destroy for team %s", team_id)
            return

        cmd = f"docker sandbox rm {shlex.quote(sandbox.sandbox_id)}"
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        del self._sandboxes[team_id]
        logger.info("Sandbox destroyed for team %s", team_id)

    async def destroy_all(self) -> None:
        """Destroy all active sandboxes. Used in cleanup/shutdown."""
        team_ids = list(self._sandboxes.keys())
        for team_id in team_ids:
            await self.destroy_sandbox(team_id)
