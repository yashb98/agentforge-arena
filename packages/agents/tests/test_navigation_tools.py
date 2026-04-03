"""Unit tests for agent-facing navigation tool wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from packages.agents.src.tools.navigation import NavigationTools
from packages.memory.src.navigation.service import SymbolHit, UsageHit


@pytest.mark.asyncio
async def test_navigation_tools_wrap_service_shapes() -> None:
    nav_service = AsyncMock()
    nav_service.find_symbol = AsyncMock(
        return_value=[SymbolHit(file_path="a.py", symbol_name="Foo", symbol_type="class")]
    )
    nav_service.where_used = AsyncMock(
        return_value=[UsageHit(file_path="a.py", line=12, snippet="x = Foo()")]
    )
    nav_service.module_map = AsyncMock(return_value={"a.py": ["os"]})
    tools = NavigationTools(nav_service)
    team_id = uuid4()
    files = ["a.py"]

    symbols = await tools.find_symbol(team_id=team_id, files=files, symbol="Foo")
    usages = await tools.where_used(team_id=team_id, files=files, symbol="Foo")
    graph = await tools.module_map(team_id=team_id, files=files)

    assert symbols == [{"file_path": "a.py", "symbol_name": "Foo", "symbol_type": "class"}]
    assert usages == [{"file_path": "a.py", "line": 12, "snippet": "x = Foo()"}]
    assert graph == {"a.py": ["os"]}
