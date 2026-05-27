import json, re
from pathlib import Path
from butler_pc_core.cards.box2 import adapter_loader as a
SHA64 = re.compile(r"^[0-9a-f]{64}$")

def test_all_sealed_shas_are_full_64_char_sha256():
    assert SHA64.match(a.BUTLER_V3_LORA_ADAPTER_SHA)
    assert SHA64.match(a.BUTLER_V3_F16_GGUF_SHA)
    assert SHA64.match(a.BUTLER_V3_Q4_K_M_GGUF_SHA)
    assert SHA64.match(a.HELPER_3_REWRITE_ADAPTER_SHA)

def test_butler_v3_lora_sha_is_full_not_abbreviated():
    assert a.BUTLER_V3_LORA_ADAPTER_SHA == "ee35fe47c2421df18597dd9939a08b4ff3bf4e25b8766ba5d914060ccaedd284"
    assert a.BUTLER_V3_LORA_ADAPTER_SHA != "ee35fe47afb6...d284"

def test_contracts_do_not_cross_compare_lora_and_gguf_shas():
    contracts = a.asset_contracts(); lora = contracts["butler_v3_lora"]
    assert lora.path_kind == "directory"
    assert lora.sha_scope == "file"
    assert contracts["butler_v3_gguf_f16"].path_kind == "file"
    assert contracts["butler_v3_gguf_q4_k_m"].path_kind == "file"
    assert lora.expected_sha256 not in {a.BUTLER_V3_F16_GGUF_SHA, a.BUTLER_V3_Q4_K_M_GGUF_SHA}

def test_sha_contract_v3_json_matches_python_constants():
    root = Path(__file__).resolve().parents[3]
    assets = json.loads((root / "evidence/box2_helper3/sha_contract_v3.json").read_text(encoding="utf-8"))["sealed_assets"]
    assert assets["butler_v3_lora"]["expected_sha256"] == a.BUTLER_V3_LORA_ADAPTER_SHA
    assert assets["butler_v3_lora"]["sha_scope"] == "file"
    assert assets["butler_v3_gguf_f16"]["expected_sha256"] == a.BUTLER_V3_F16_GGUF_SHA
    assert assets["butler_v3_gguf_q4_k_m"]["expected_sha256"] == a.BUTLER_V3_Q4_K_M_GGUF_SHA
    assert assets["helper_3"]["expected_sha256"] == a.HELPER_3_REWRITE_ADAPTER_SHA
