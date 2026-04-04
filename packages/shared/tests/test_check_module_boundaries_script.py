"""Smoke tests for scripts/check_module_boundaries.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "check_module_boundaries.py"


def test_module_boundaries_no_modules_json_exits_zero(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_module_boundaries_detects_disallowed_import(tmp_path: Path) -> None:
    modules = {
        "modules": [
            {
                "module_name": "alpha",
                "paths": ["alpha"],
                "public_entrypoints": ["alpha"],
                "depends_on": [],
            },
            {
                "module_name": "beta",
                "paths": ["beta"],
                "public_entrypoints": ["beta"],
                "depends_on": [],
            },
        ]
    }
    (tmp_path / "MODULES.json").write_text(json.dumps(modules), encoding="utf-8")
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "use.py").write_text("import beta\n", encoding="utf-8")
    (tmp_path / "beta").mkdir()
    (tmp_path / "beta" / "__init__.py").write_text("\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "beta" in result.stdout or "beta" in result.stderr
