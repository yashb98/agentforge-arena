"""Agent-facing wrappers around memory navigation service."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from packages.memory.src.navigation.service import NavigationService


class NavigationTools:
    """Tool surface used by agent runtime for codebase navigation."""

    def __init__(self, navigation_service: NavigationService) -> None:
        self._navigation = navigation_service

    async def find_symbol(
        self,
        *,
        team_id: UUID,
        files: Sequence[str],
        symbol: str,
    ) -> list[dict[str, str]]:
        rows = await self._navigation.find_symbol(team_id=team_id, files=files, symbol=symbol)
        return [
            {
                "file_path": row.file_path,
                "symbol_name": row.symbol_name,
                "symbol_type": row.symbol_type,
            }
            for row in rows
        ]

    async def where_used(
        self,
        *,
        team_id: UUID,
        files: Sequence[str],
        symbol: str,
    ) -> list[dict[str, str | int]]:
        rows = await self._navigation.where_used(team_id=team_id, files=files, symbol=symbol)
        return [
            {
                "file_path": row.file_path,
                "line": row.line,
                "snippet": row.snippet,
            }
            for row in rows
        ]

    async def module_map(
        self,
        *,
        team_id: UUID,
        files: Sequence[str],
    ) -> dict[str, list[str]]:
        return await self._navigation.module_map(team_id=team_id, files=files)
