"""Execute LLM tool calls against navigation and memory services."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from packages.agents.src.tools.navigation import NavigationTools
from packages.shared.src.types.models import AgentRole

logger = logging.getLogger(__name__)

_MAX_NAV_FILES = 400


class AgentToolExecutor:
    """Runs tool calls with path confinement to the agent workspace."""

    def __init__(
        self,
        *,
        team_id: UUID,
        agent_id: UUID,
        role: AgentRole,
        workspace_path: str,
        navigation_tools: NavigationTools | None,
        memory_manager: object | None,
    ) -> None:
        self._team_id = team_id
        self._agent_id = agent_id
        self._role = role
        self._root = Path(workspace_path).resolve()
        self._navigation = navigation_tools
        self._memory = memory_manager

    def _collect_py_files(self, file_globs: list[str] | None) -> list[str]:
        if not self._root.is_dir():
            return []
        files: list[str] = []
        if file_globs:
            for pattern in file_globs:
                for p in self._root.glob(pattern):
                    if p.is_file() and p.suffix == ".py":
                        resolved = p.resolve()
                        try:
                            resolved.relative_to(self._root)
                        except ValueError:
                            continue
                        files.append(str(resolved))
        else:
            for p in self._root.rglob("*.py"):
                if p.is_file():
                    resolved = p.resolve()
                    try:
                        resolved.relative_to(self._root)
                    except ValueError:
                        continue
                    files.append(str(resolved))
        dedup = sorted(set(files))
        return dedup[:_MAX_NAV_FILES]

    async def execute(self, name: str, raw_arguments: str) -> str:
        try:
            args: dict[str, Any] = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"invalid JSON arguments: {e}"})

        try:
            if name == "nav_find_symbol":
                if self._navigation is None:
                    return json.dumps({"error": "navigation tools not available"})
                symbol = args.get("symbol")
                if not isinstance(symbol, str) or not symbol:
                    return json.dumps({"error": "symbol is required"})
                globs = args.get("file_globs")
                file_globs = globs if isinstance(globs, list) else None
                files = self._collect_py_files(
                    [str(x) for x in file_globs] if file_globs else None
                )
                hits = await self._navigation.find_symbol(
                    team_id=self._team_id, files=files, symbol=symbol
                )
                return json.dumps({"hits": hits})

            if name == "nav_where_used":
                if self._navigation is None:
                    return json.dumps({"error": "navigation tools not available"})
                symbol = args.get("symbol")
                if not isinstance(symbol, str) or not symbol:
                    return json.dumps({"error": "symbol is required"})
                globs = args.get("file_globs")
                file_globs = globs if isinstance(globs, list) else None
                files = self._collect_py_files(
                    [str(x) for x in file_globs] if file_globs else None
                )
                hits = await self._navigation.where_used(
                    team_id=self._team_id, files=files, symbol=symbol
                )
                return json.dumps({"usages": hits})

            if name == "nav_module_map":
                if self._navigation is None:
                    return json.dumps({"error": "navigation tools not available"})
                globs = args.get("file_globs")
                file_globs = globs if isinstance(globs, list) else None
                files = self._collect_py_files(
                    [str(x) for x in file_globs] if file_globs else None
                )
                graph = await self._navigation.module_map(
                    team_id=self._team_id, files=files
                )
                return json.dumps({"graph": graph})

            if name == "memory_recall":
                if self._memory is None:
                    return json.dumps({"error": "memory not available"})
                query = args.get("query")
                if not isinstance(query, str) or not query:
                    return json.dumps({"error": "query is required"})
                ctx = await self._memory.recall(self._agent_id, self._role, query=query)
                return json.dumps(ctx, default=str)

        except Exception:
            logger.exception("Tool %s failed", name)
            return json.dumps({"error": "tool execution failed"})

        return json.dumps({"error": f"unknown tool: {name}"})
