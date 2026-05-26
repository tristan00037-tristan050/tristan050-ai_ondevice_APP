import importlib.util

from butler_pc_core.cards.box2.model_chain import (
    REQUIRED_OUTPUT_FIELDS,
    build_model_chain_status,
    build_rewrite_system_prompt,
    contract_only_rewrite,
    validate_rewrite_output,
)


def test_model_chain_status_contains_runtime_fields(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    status = build_model_chain_status(allow_missing_assets=True)
    payload = status.to_dict()
    assert "runtime_available" in payload
    assert "runtime_packages" in payload
    assert payload["external_send"] == 0
    assert payload["raw_persistence"] == 0
    assert payload["retraining"] is False
    assert payload["adapter_changed"] is False
    assert payload["model_weight_changed"] is False


def test_system_prompt_requires_all_8_fields_and_no_external_send():
    prompt = build_rewrite_system_prompt()
    for field in REQUIRED_OUTPUT_FIELDS:
        assert field in prompt
    assert "Never transmit content externally" in prompt
    assert "Never persist raw source text" in prompt


def test_validate_rewrite_output_rejects_missing_or_extra_fields():
    valid_payload = {field: "" for field in REQUIRED_OUTPUT_FIELDS}
    assert validate_rewrite_output(valid_payload)["valid"] is True

    missing_payload = dict(valid_payload)
    missing_payload.pop("최종 문안")
    assert validate_rewrite_output(missing_payload)["valid"] is False

    extra_payload = dict(valid_payload)
    extra_payload["foreign_doc"] = "raw"
    assert validate_rewrite_output(extra_payload)["valid"] is False


def test_contract_only_rewrite_does_not_return_or_persist_raw_text(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    foreign = "민감 원문 A"
    fmt = "내부 양식 B"
    response = contract_only_rewrite(foreign_doc_text=foreign, our_format_text=fmt)
    assert response["external_send"] == 0
    assert response["raw_persistence"] == 0
    assert response["contract_only"] is True
    dumped = str(response)
    assert foreign not in dumped
    assert fmt not in dumped
    assert response["input_digests"]["foreign_doc_digest"].startswith("sha256:")
