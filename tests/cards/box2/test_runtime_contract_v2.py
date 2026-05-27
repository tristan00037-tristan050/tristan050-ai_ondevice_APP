import importlib.util, json
from pathlib import Path
from butler_pc_core.cards.box2 import model_chain as m
from butler_pc_core.cards.box2.runtime_loader import detect_runtime_packages, load_runtime

def test_runtime_contract_json_declares_required_packages():
    root = Path(__file__).resolve().parents[3]
    payload = json.loads((root / "evidence/box2_helper3/runtime_contract_v3.json").read_text(encoding="utf-8"))
    assert payload["required_packages"] == ["mlx-lm", "peft", "transformers"]
    assert payload["required_import_modules"] == {"mlx_lm": "mlx_lm", "peft": "peft", "transformers": "transformers"}
    assert payload["break_system_packages_default"] is False
    assert payload["skip_is_not_full_pass"] is True

def test_runtime_detection_uses_importable_modules(monkeypatch):
    def fake_find_spec(name): return object() if name in {"mlx_lm", "transformers"} else None
    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    status = m.detect_runtime_packages()
    assert status.to_dict() == {"mlx_lm": True, "peft": False, "transformers": True}
    assert status.all_available is False
    assert detect_runtime_packages()["fail_class"] == "PARTIAL_DONE_V3_RUNTIME_INSTALL_FAILED"

def test_runtime_missing_yields_contract_only_not_real_pass(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    status = m.build_model_chain_status(allow_missing_assets=True)
    assert status.runtime_available is False
    assert status.load_mode in {"contract_only", "blocked"}
    assert "PASS_V2_FULL" not in status.status

def test_runtime_all_available_still_respects_asset_state(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    status = m.build_model_chain_status(allow_missing_assets=True)
    assert status.runtime_available is True
    assert status.runtime_packages == {"mlx_lm": True, "peft": True, "transformers": True}
    assert status.load_mode in {"contract_only", "real_load_ready", "blocked"}

def test_load_runtime_schema_when_missing_or_available():
    payload = load_runtime()
    assert payload["schema_version"] == "box2.helper3.runtime.v3"
    assert set(payload["runtime_packages"]) == {"mlx_lm", "peft", "transformers"}
    assert "python_version" in payload
    assert "platform" in payload
