"""Unit tests for navigation service and module graph behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.indexer.parser import CodeParser
from packages.memory.src.navigation.service import NavigationService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_find_symbol_and_where_used(tmp_path: Path) -> None:
    file_path = tmp_path / "app.py"
    file_path.write_text(
        "from services.core import helper\n"
        "\n"
        "def do_work() -> None:\n"
        "    helper()\n"
        "\n"
        "def caller() -> None:\n"
        "    do_work()\n",
        encoding="utf-8",
    )
    svc = NavigationService(CodeParser(GrammarLoader()))
    team_id = uuid4()
    files = [str(file_path)]

    symbols = await svc.find_symbol(team_id=team_id, files=files, symbol="do_work")
    usages = await svc.where_used(team_id=team_id, files=files, symbol="do_work")

    assert len(symbols) == 1
    assert symbols[0].symbol_type == "function"
    assert len(usages) == 1
    assert usages[0].line == 7


@pytest.mark.asyncio
async def test_module_map_extracts_import_dependencies(tmp_path: Path) -> None:
    file_path = tmp_path / "worker.py"
    file_path.write_text(
        "import os\n"
        "from packages.shared.src.config import get_settings\n"
        "\n"
        "def run() -> None:\n"
        "    _ = os.getcwd()\n"
        "    _ = get_settings()\n",
        encoding="utf-8",
    )
    svc = NavigationService(CodeParser(GrammarLoader()))
    graph = await svc.module_map(team_id=uuid4(), files=[str(file_path)])

    deps = graph[str(file_path)]
    assert "os" in deps
    assert "packages.shared.src.config" in deps
