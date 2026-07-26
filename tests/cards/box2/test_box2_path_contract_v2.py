from pathlib import Path

from butler_pc_core.cards.box2 import adapter_loader as a


def test_default_handoff_root_is_logical_asset_capability():
    assert a.DEFAULT_HANDOFF_ROOT == "asset://box2.adapter"


def test_legacy_direct_qwen_root_is_not_used_in_contract_constants():
    constants = [
        a.DEFAULT_HANDOFF_ROOT,
        a.DEFAULT_BASE_MODEL_PATH,
        a.DEFAULT_BUTLER_V3_LORA_PATH,
        a.DEFAULT_BUTLER_V3_GGUF_F16_PATH,
        a.DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH,
        a.DEFAULT_HELPER_3_PATH,
    ]
    assert ("~/Desktop/도우미폴더/" + "Qwen3-1.7B") not in constants
    assert all(path.startswith(a.DEFAULT_HANDOFF_ROOT) or path == a.DEFAULT_HANDOFF_ROOT for path in constants)


def test_helper3_path_is_under_handoff_root():
    assert a.DEFAULT_HELPER_3_PATH.startswith(a.DEFAULT_HANDOFF_ROOT + "/")


def test_butler_v3_lora_and_gguf_paths_are_split_constants():
    assert a.DEFAULT_BUTLER_V3_LORA_PATH != a.DEFAULT_BUTLER_V3_GGUF_F16_PATH
    assert a.DEFAULT_BUTLER_V3_LORA_PATH != a.DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH
    assert a.DEFAULT_BUTLER_V3_LORA_PATH.endswith("/butler_adapter")
    assert a.DEFAULT_BUTLER_V3_GGUF_F16_PATH.endswith("/model_f16")
    assert a.DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH.endswith("/model_q4")


def test_no_source_file_contains_forbidden_legacy_root():
    root = Path(__file__).resolve().parents[3]
    forbidden = "~/Desktop/도우미폴더/" + "Qwen3-1.7B"
    offenders = []
    for path in root.rglob("*"):
        if "__pycache__" in path.parts:
            continue
        if path.is_file() and path.suffix in {".py", ".json", ".md", ".sh", ".txt"}:
            if forbidden in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []
