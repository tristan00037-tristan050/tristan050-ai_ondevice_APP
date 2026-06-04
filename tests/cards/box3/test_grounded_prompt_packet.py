from __future__ import annotations

import json
import pytest

from butler_pc_core.cards.box3.grounded_prompt import (
    ABSTAINED_SLOT_TEXT,
    DecodeConfig,
    Box3PromptContractError,
    build_grounded_prompt_packet,
    evaluate_usefulness_gate,
)
from butler_pc_core.cards.box3.rag_context import build_rag_context_packet, sha256_text


class Envelope:
    request_id = "req-test"
    drafting_request_runtime_only = "담당자와 날짜를 포함해 초안을 작성하세요."
    reference_text_runtime_only = ["납품 일정은 2026년 6월 10일입니다."]

    @property
    def request_digest(self):
        return sha256_text(self.drafting_request_runtime_only)


class Verdict:
    def __init__(self, level):
        self.support_level = level


def test_decode_config_blocks_drift():
    with pytest.raises(Box3PromptContractError):
        DecodeConfig(temperature=0.7).to_dict()
    with pytest.raises(Box3PromptContractError):
        DecodeConfig(top_p=0.95).to_dict()
    with pytest.raises(Box3PromptContractError):
        DecodeConfig(repeat_penalty=1.0).to_dict()


def test_grounded_prompt_persistable_is_digest_only():
    rag = build_rag_context_packet(Envelope(), None)
    packet = build_grounded_prompt_packet(Envelope(), rag)
    persisted = packet.to_persistable_dict()
    encoded = json.dumps(persisted, ensure_ascii=False)
    assert "납품" not in encoded
    assert "담당자" not in encoded
    assert persisted["prompt_digest"].startswith("sha256:")
    assert persisted["decode_config_digest"].startswith("sha256:")
    assert len(persisted["fewshot_ids"]) == 3
    assert ABSTAINED_SLOT_TEXT in packet.prompt_runtime_only


def test_usefulness_gate_blocks_unsupported_and_partial_for_empty():
    blocked = evaluate_usefulness_gate(
        "제목: 초안\n배경: x\n핵심 내용: x\n근거: x\n확인 필요: x\n최종 문안: x",
        [Verdict("unsupported")],
    )
    assert blocked.status == "BLOCK"
    partial = evaluate_usefulness_gate("제목: 초안", [Verdict("supported")])
    assert partial.status == "PARTIAL"
    ok = evaluate_usefulness_gate(
        "제목: 초안\n배경: x\n핵심 내용: x\n근거: x\n확인 필요: x\n최종 문안: x",
        [Verdict("supported")],
    )
    assert ok.status == "PASS"
