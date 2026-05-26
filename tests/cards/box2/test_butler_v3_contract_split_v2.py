import json
import re
from pathlib import Path

from butler_pc_core.cards.box2 import adapter_loader as a


SHA64 = re.compile(r"^[0-9a-f]{64}$")


def test_gguf_file_shas_are_full_64_char_sha256():
    assert SHA64.match(a.BUTLER_V3_F16_GGUF_SHA)
    assert SHA64.match(a.BUTLER_V3_Q4_K_M_GGUF_SHA)
    assert SHA64.match(a.HELPER_3_REWRITE_ADAPTER_SHA)


def test_butler_v3_lora_sha_is_not_abbreviated_or_fake_sealed():
    assert a.BUTLER_V3_LORA_ADAPTER_SHA is None or SHA64.match(a.BUTLER_V3_LORA_ADAPTER_SHA)
    assert a.BUTLER_V3_LORA_ADAPTER_SHA != "ee35fe47afb6...d284"


def test_contracts_do_not_cross_compare_lora_and_gguf_shas():
    contracts = a.asset_contracts()
    lora = contracts["butler_v3_lora"]
    f16 = contracts["butler_v3_gguf_f16"]
    q4 = contracts["butler_v3_gguf_q4_k_m"]
    assert lora.path_kind == "directory"
    assert f16.path_kind == "file"
    assert q4.path_kind == "file"
    assert lora.expected_sha256 not in {a.BUTLER_V3_F16_GGUF_SHA, a.BUTLER_V3_Q4_K_M_GGUF_SHA}


def test_sha_contract_v2_json_matches_python_constants():
    root = Path(__file__).resolve().parents[3]
    payload = json.loads((root / "evidence/box2_helper3/sha_contract_v2.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "box2.helper3.sha_contract.v2"
    assert payload["butler_v3_lora"]["path_kind"] == "directory"
    assert payload["butler_v3_lora"]["expected_sha256"] is None
    assert payload["butler_v3_gguf_f16"]["expected_sha256"] == a.BUTLER_V3_F16_GGUF_SHA
    assert payload["butler_v3_gguf_f16"]["sha_scope"] == "file"
    assert payload["butler_v3_gguf_q4_k_m"]["expected_sha256"] == a.BUTLER_V3_Q4_K_M_GGUF_SHA
    assert payload["butler_v3_gguf_q4_k_m"]["sha_scope"] == "file"
    assert payload["helper_3"]["expected_sha256"] == a.HELPER_3_REWRITE_ADAPTER_SHA
