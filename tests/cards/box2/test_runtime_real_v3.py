import pytest
pytest.importorskip("mlx_lm")
pytest.importorskip("peft")
pytest.importorskip("transformers")
from butler_pc_core.cards.box2.runtime_loader import load_runtime

def test_runtime_real_v3_imports_all_required_packages():
    payload = load_runtime()
    assert payload["runtime_available"] is True
    assert payload["runtime_packages"] == {"mlx_lm": True, "peft": True, "transformers": True}
    assert payload["fail_class"] is None
