import pytest

from butler_pc_core.cards.box3.draft_service import (
    BOX3_CURRENT_CONTRACT_FIELDS,
    BOX3_DRAFT_ENDPOINT,
    Box3ContractError,
    compose_box3_current_contract_input,
    draft_from_current_contract,
    validate_digest_only_contract_input,
)


def test_box3_current_main_endpoint_contract_is_preserved():
    payload = compose_box3_current_contract_input(
        reference_doc_digests=["sha256:" + "a" * 64],
        request_digest="sha256:" + "b" * 64,
        format_hint="report",
        max_new_tokens=128,
    )
    assert BOX3_DRAFT_ENDPOINT == "/v1/cards/3/draft"
    assert tuple(payload.keys()) == BOX3_CURRENT_CONTRACT_FIELDS
    assert payload["max_new_tokens"] == 128
    result = draft_from_current_contract(**payload)
    assert result["status"] == "contract_only"
    assert result["external_send_zero"] is True
    assert result["raw_saved_zero"] is True
    assert result["real_claim_allowed"] is False


def test_box3_current_contract_rejects_unsafe_text():
    with pytest.raises(Exception) as exc:
        draft_from_current_contract(
            input_text="sk-proj-secret-token-123456789",
            prompt_template="Input: {input}",
            max_new_tokens=128,
        )
    assert "BLOCK_RUNTIME_TEXT_FORBIDDEN" in str(exc.value)


def test_box3_current_contract_bounds_max_new_tokens():
    with pytest.raises(Box3ContractError):
        draft_from_current_contract(input_text="digest only", prompt_template="Input: {input}", max_new_tokens=0)
    with pytest.raises(Box3ContractError):
        draft_from_current_contract(input_text="digest only", prompt_template="Input: {input}", max_new_tokens=2048)


def test_real_runner_requires_composed_digest_only_input():
    def runner(prompt, max_new_tokens):
        return "제목\n배경\n핵심 내용\n근거\n확인 필요\n최종 문안\n합니다"

    with pytest.raises(Box3ContractError) as exc:
        draft_from_current_contract(
            input_text="ordinary business prose without pii still must not reach runner",
            prompt_template="Input: {input}",
            max_new_tokens=128,
            real_model_runner=runner,
        )
    assert "DIGEST_ONLY_INPUT_REQUIRED_FOR_REAL_RUNNER" in str(exc.value)


def test_real_runner_accepts_only_composed_digest_shape():
    payload = compose_box3_current_contract_input(
        reference_doc_digests=["sha256:" + "a" * 64],
        request_digest="sha256:" + "b" * 64,
        max_new_tokens=128,
    )
    parsed = validate_digest_only_contract_input(payload["input_text"])
    assert parsed["request_digest"] == "sha256:" + "b" * 64

    def runner(prompt, max_new_tokens):
        assert "BOX3_DIGEST_ONLY_INPUT" in prompt
        assert "ordinary business prose" not in prompt
        return "제목\n배경\n핵심 내용\n근거\n확인 필요\n최종 문안\n합니다"

    result = draft_from_current_contract(**payload, real_model_runner=runner)
    assert result["status"] == "real"
    assert result["contract_only"] is False
    assert result["real_claim_allowed"] is True
