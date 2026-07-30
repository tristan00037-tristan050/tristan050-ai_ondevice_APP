from pathlib import Path

from butler_pc_core.cards.box2 import adapter_loader as a


def test_default_root_is_the_bundled_box2_resource():
    assert a.DEFAULT_HANDOFF_ROOT == "models/box2"


def test_developer_paths_are_not_used_in_contract_constants():
    constants = [
        a.DEFAULT_HANDOFF_ROOT,
        a.DEFAULT_BASE_MODEL_PATH,
        a.DEFAULT_BUTLER_V3_LORA_PATH,
        a.DEFAULT_BUTLER_V3_GGUF_F16_PATH,
        a.DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH,
        a.DEFAULT_HELPER_3_PATH,
    ]
    assert all("Desktop/" not in path for path in constants)
    assert all("/Volumes/" not in path for path in constants)
    assert all(path.startswith(a.DEFAULT_HANDOFF_ROOT) or path == a.DEFAULT_HANDOFF_ROOT for path in constants)


def test_helper3_default_path_is_under_bundled_root():
    assert a.DEFAULT_HELPER_3_PATH.startswith(a.DEFAULT_HANDOFF_ROOT + "/")
    assert a.DEFAULT_HELPER_3_PATH.endswith(
        "box2_adapter/rewrite/adapter/box2b_v5_rewrite"
    )


def test_helper3_environment_path_precedes_bundle(tmp_path, monkeypatch):
    configured = tmp_path / "configured-helper3"
    monkeypatch.setenv("BUTLER_BOX2_HELPER3_ADAPTER_PATH", str(configured))

    contract = a.asset_contracts()["helper_3"]

    assert contract.path == str(configured / "adapter_model.safetensors")
    assert contract.path_source == "environment"


def test_helper3_uses_bundle_when_environment_is_unset(monkeypatch):
    monkeypatch.delenv("BUTLER_BOX2_HELPER3_ADAPTER_PATH", raising=False)

    contract = a.asset_contracts()["helper_3"]

    assert contract.path_source == "bundle"
    assert contract.path.endswith(
        "models/box2/box2_adapter/rewrite/adapter/"
        "box2b_v5_rewrite/adapter_model.safetensors"
    )


def test_butler_v3_lora_and_gguf_paths_are_split_constants():
    assert a.DEFAULT_BUTLER_V3_LORA_PATH != a.DEFAULT_BUTLER_V3_GGUF_F16_PATH
    assert a.DEFAULT_BUTLER_V3_LORA_PATH != a.DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH
    assert a.DEFAULT_BUTLER_V3_LORA_PATH.endswith("/butler_v3_preserved")
    assert a.DEFAULT_BUTLER_V3_GGUF_F16_PATH.endswith(".gguf")
    assert a.DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH.endswith(".gguf")


def test_box2_source_contains_no_developer_machine_path():
    root = Path(__file__).resolve().parents[3]
    offenders = []
    for path in (root / "butler_pc_core/cards/box2").rglob("*"):
        if "__pycache__" in path.parts:
            continue
        if path.is_file() and path.suffix in {".py", ".json", ".md", ".sh", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "Desktop/" in text or "/Volumes/" in text:
                offenders.append(str(path.relative_to(root)))
    assert offenders == []
