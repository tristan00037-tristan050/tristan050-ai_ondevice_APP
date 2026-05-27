import os
from pathlib import Path
import pytest
from butler_pc_core.cards.box2.real_load_smoke import run_real_load_smoke


def test_real_load_smoke_v3_three_stage_local_run():
    if os.environ.get("BUTLER_BOX2_RUN_REAL_V3") != "1":
        pytest.skip("set BUTLER_BOX2_RUN_REAL_V3=1 on the MacBook runtime host")
    root = Path(__file__).resolve().parents[3]
    payload = run_real_load_smoke(evidence_path=root / "evidence/box2_helper3/real_load_smoke_v3.json")
    assert payload["fail_class"] is None
    assert payload["status"] == "PASS_V3_REAL_LOAD_SMOKE"
    assert payload["stages_loaded"] == ["base", "butler_v3", "helper_3"]
    assert payload["multi_lora_strategy"] in {"set_adapter_list", "weighted_adapter", "sequential_scratch_merge"}
    assert payload["inference_count"] == 1
    assert payload["output_digest_only"] is True
    assert payload["raw_output_saved"] is False
