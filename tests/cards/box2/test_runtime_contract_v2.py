import importlib.util
import json
from pathlib import Path

from butler_pc_core.cards.box2 import model_chain as m


def test_runtime_contract_json_declares_required_packages():
    root = Path(__file__).resolve().parents[3]
    payload = json.loads((root / "evidence/box2_helper3/runtime_contract_v2.json").read_text(encoding="utf-8"))
    assert payload["required_packages"] == ["mlx-lm", "peft", "transformers"]
    assert payload["required_import_modules"] == {"mlx_lm": "mlx_lm", "peft": "peft", "transformers": "transformers"}
    assert payload["break_system_packages_default"] is False


def test_runtime_detection_uses_importable_modules(monkeypatch):
    def fake_find_spec(name):
        return object() if name in {"mlx_lm", "transformers"} else None

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    status = m.detect_runtime_packages()
    assert status.to_dict() == {"mlx_lm": True, "peft": False, "transformers": True}
    assert status.all_available is False


def test_runtime_missing_yields_contract_only_not_real_pass(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    status = m.build_model_chain_status(allow_missing_assets=True)
    assert status.runtime_available is False
    assert status.load_mode in {"contract_only", "blocked"}
    assert "PASS_V2_REAL_LOAD_READY" not in status.status


def test_runtime_all_available_still_respects_asset_or_lora_pending(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    status = m.build_model_chain_status(allow_missing_assets=True)
    assert status.runtime_available is True
    assert status.runtime_packages == {"mlx_lm": True, "peft": True, "transformers": True}
    assert status.load_mode in {"contract_only", "real_load_ready", "blocked"}
    if status.load_mode != "real_load_ready":
        assert "PASS_V2_REAL_LOAD_READY" not in status.status
