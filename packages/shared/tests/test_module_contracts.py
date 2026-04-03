"""Module boundary contract typing."""

from __future__ import annotations

from packages.shared.src.types.module_contracts import ModuleManifestDict


def test_module_manifest_dict_typed_shape() -> None:
    m: ModuleManifestDict = {
        "module_name": "ingestion",
        "public_entrypoints": ["ingestion.api"],
        "depends_on": ["shared.types"],
    }
    assert m["module_name"] == "ingestion"
    assert "shared.types" in m["depends_on"]
