from __future__ import annotations


def test_inference_has_verify_and_locate_adapter():
    import src.butler.card5.inference as inference

    assert hasattr(inference, "verify_and_locate_adapter")
    assert callable(inference.verify_and_locate_adapter)


def test_inference_verify_and_locate_adapter_monkeypatchable(monkeypatch):
    import src.butler.card5.inference as inference

    called = {"value": False}

    def fake_verify(*args, **kwargs):
        called["value"] = True
        return kwargs.get("adapter_path") or "fake-adapter"

    monkeypatch.setattr(inference, "verify_and_locate_adapter", fake_verify)
    assert inference.verify_and_locate_adapter(adapter_path="x") == "x"
    assert called["value"] is True

