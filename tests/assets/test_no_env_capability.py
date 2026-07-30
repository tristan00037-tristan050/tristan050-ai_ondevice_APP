from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.no_sidecar_token
PRODUCT_ROOTS = (
    ROOT / "butler_pc_core",
    ROOT / "butler_sidecar.py",
    ROOT / "butler-desktop/src-tauri/src",
    ROOT / "butler-desktop/src-tauri/tauri.conf.json",
)
FORBIDDEN_CAPABILITIES = (
    "PYTEST_" + "CURRENT_TEST",
    "HELPER1_" + "SDK_PATH",
    "BGE_M3_" + "MODEL_DIR",
    "BUTLER_BOX3_" + "BASE_MODEL_PATH",
    "BUTLER_BOX3_" + "V9_Q4_MODEL_PATH",
    "BUTLER_HELPER4_" + "SDK_PATH",
    "BUTLER_HELPER7_" + "SDK_PATH",
    "BUTLER_HELPER8_" + "SDK_PATH",
    "BUTLER_ASSET_" + "ROOT",
)


def _product_sources() -> list[Path]:
    result: list[Path] = []
    for root in PRODUCT_ROOTS:
        if root.is_dir():
            result.extend(root.rglob("*.py"))
            result.extend(root.rglob("*.rs"))
        else:
            result.append(root)
    return sorted(set(result))


def test_product_code_has_no_env_capability() -> None:
    offenders: list[str] = []
    for path in _product_sources():
        raw = path.read_text(encoding="utf-8", errors="strict")
        if any(name in raw for name in FORBIDDEN_CAPABILITIES):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
