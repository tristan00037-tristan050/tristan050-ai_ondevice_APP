from butler_pc_core.cards.box2 import model_chain as mc


def _runtime_import_failure_payload():
    return {
        "schema_version": "box2.helper3.runtime.v3",
        "runtime_available": False,
        "runtime_packages": {"mlx_lm": False, "peft": False, "transformers": False},
        "package_versions": {"mlx_lm": "0", "peft": "0", "transformers": "0"},
        "python_version": "3.x",
        "platform": "test",
        "fail_class": "PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR",
        "error_class": "SubprocessImportFailed",
        "import_returncodes": {"mlx_lm": 134, "peft": 0, "transformers": 0},
    }


def _runtime_success_payload():
    return {
        "schema_version": "box2.helper3.runtime.v3",
        "runtime_available": True,
        "runtime_packages": {"mlx_lm": True, "peft": True, "transformers": True},
        "package_versions": {"mlx_lm": "0", "peft": "0", "transformers": "0"},
        "python_version": "3.x",
        "platform": "test",
        "fail_class": None,
    }


def test_model_chain_status_uses_subprocess_probed_runtime_failure(monkeypatch):
    monkeypatch.setattr(mc, "load_runtime", _runtime_import_failure_payload)
    monkeypatch.setattr(mc, "verify_asset_contracts", lambda allow_missing=True: {})

    status = mc.build_model_chain_status(allow_missing_assets=True)

    assert status.runtime_available is False
    assert status.runtime_packages == {"mlx_lm": False, "peft": False, "transformers": False}
    assert status.load_mode != "real_load_ready"
    assert status.status == "PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR"
    assert "PASS_V3_REAL_LOAD_READY" not in status.status
    assert any("PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR" in reason for reason in status.blocking_reasons)


def test_contract_only_rewrite_does_not_call_runner_when_runtime_probe_fails(monkeypatch):
    monkeypatch.setattr(mc, "load_runtime", _runtime_import_failure_payload)
    monkeypatch.setattr(mc, "verify_asset_contracts", lambda allow_missing=True: {})

    called = {"value": False}

    def runner(_text: str) -> str:
        called["value"] = True
        return "{}"

    response = mc.contract_only_rewrite(
        foreign_doc_text="foreign",
        our_format_text="format",
        runner=runner,
    )

    assert called["value"] is False
    assert response["contract_only"] is True
    assert response["status"] == "PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR"
    assert response["load_mode"] == "contract_only"


def test_model_chain_status_can_mark_real_load_ready_only_after_probe_success(monkeypatch):
    monkeypatch.setattr(mc, "load_runtime", _runtime_success_payload)
    monkeypatch.setattr(mc, "verify_asset_contracts", lambda allow_missing=True: {})

    status = mc.build_model_chain_status(allow_missing_assets=True)

    assert status.runtime_available is True
    assert status.load_mode == "real_load_ready"
    assert status.status == "PASS_V3_REAL_LOAD_READY"
