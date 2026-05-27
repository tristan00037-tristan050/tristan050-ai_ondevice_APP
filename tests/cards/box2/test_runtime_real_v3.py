import pytest
from butler_pc_core.cards.box2.runtime_loader import load_runtime


def test_runtime_real_v3_imports_all_required_packages():
    payload = load_runtime()
    if not payload["runtime_available"]:
        pytest.skip(payload["fail_class"])
    assert payload["runtime_available"] is True
    assert payload["runtime_packages"] == {"mlx_lm": True, "peft": True, "transformers": True}
    assert payload["fail_class"] is None
