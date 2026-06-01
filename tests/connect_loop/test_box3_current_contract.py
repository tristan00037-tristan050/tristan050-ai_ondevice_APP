import pytest

from butler_pc_core.cards.box3.draft_service import (
    BOX3_CURRENT_CONTRACT_FIELDS,
    BOX3_DRAFT_ENDPOINT,
    Box3ContractError,
    compose_box3_current_contract_input,
    draft_from_current_contract,
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

