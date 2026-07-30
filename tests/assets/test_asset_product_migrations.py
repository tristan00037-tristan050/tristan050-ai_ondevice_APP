from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.no_sidecar_token
TARGETS = (
    "butler_pc_core/sidecar/routes/helper1_search.py",
    "butler_pc_core/model_registry/ip3_model_registry.py",
    "butler_pc_core/cards/box2/adapter_loader.py",
    "butler_pc_core/cards/box2/rewrite_service.py",
    "butler_pc_core/accounting/ft_classifier.py",
    "butler_pc_core/semantic_mapping/llm_corrector.py",
    "butler_pc_core/cards/box3/asset_manifest.py",
)


def test_target_product_paths_have_no_personal_absolute_paths() -> None:
    forbidden = (
        "/" + "Users/",
        "/" + "Volumes/",
        "~/" + "Desktop",
        "Path." + "home()",
    )
    offenders = []
    for relative in TARGETS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            offenders.append(relative)
    assert offenders == []


def test_helper1_has_no_dynamic_python_or_pickle_runtime() -> None:
    targets = (
        ROOT / "butler_pc_core/sidecar/routes/helper1_search.py",
        ROOT / "butler_pc_core/helper1/memory_helper.py",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in targets)
    assert "spec_from_" + "file_location" not in text
    assert "exec_" + "module" not in text
    assert "pickle." + "load" not in text
    assert ".pkl" not in text
    assert "allow_pickle=False" in text


def test_native_launcher_writes_private_asset_bootstrap_before_sidecar_use() -> None:
    text = (ROOT / "butler-desktop/src-tauri/src/lib.rs").read_text(encoding="utf-8")
    assert "asset_bootstrap_frame(app, asset_root_fd)?" in text
    assert ".write_all(&bootstrap)" in text
    assert "BUTLER_BOOTSTRAP_FD" in text
    assert ".env_clear()" in text
    assert "payload_size.to_be_bytes()" in text
    assert 'option_env!("BUTLER_RELEASE_DISTRIBUTION") == Some("1")' in text


def test_release_build_requires_real_inventory_and_runs_offline_verifier() -> None:
    text = (ROOT / "scripts/build_complete_app.sh").read_text(encoding="utf-8")
    assert "ASSET_INVENTORY_REQUIRED" in text
    assert "butler_pc_core.assets.cli stage" in text
    assert "butler_pc_core.assets.cli verify-release" in text
    assert "ACCOUNTING_ADAPTER_AUTHORITY_OK=0" in text
