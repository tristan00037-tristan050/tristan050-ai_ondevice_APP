from __future__ import annotations

import json

from butler_pc_core.cards.box3.rag_context import (
    RuntimeEvidenceUnit,
    build_rag_context_packet,
    sha256_text,
)


class Envelope:
    request_id = "req-test"
    drafting_request_runtime_only = "납품 일정과 담당자, 금액을 포함해 보고서 초안을 작성하세요."
    reference_text_runtime_only = [
        "납품 일정은 2026년 6월 10일입니다.\n금액은 300만원입니다.\n이전 지시를 무시하라는 문장은 문서 내 지시입니다."
    ]

    @property
    def request_digest(self):
        return sha256_text(self.drafting_request_runtime_only)


def test_rag_context_persistable_has_no_raw_text():
    packet = build_rag_context_packet(Envelope(), None)
    persisted = packet.to_persistable_dict()
    encoded = json.dumps(persisted, ensure_ascii=False)
    assert "납품" not in encoded
    assert "이전 지시" not in encoded
    assert persisted["raw_saved_zero"] is True
    assert persisted["evidence_unit_count"] >= 1
    assert persisted["selected_evidence_markers"]


def test_rag_context_marks_absent_slots():
    packet = build_rag_context_packet(Envelope(), None)
    assert "owner" in packet.absent_slots
    assert "amount" not in packet.absent_slots
    assert "date" not in packet.absent_slots


def test_rag_injection_defense_marks_budget():
    packet = build_rag_context_packet(Envelope(), None)
    assert packet.token_budget["injection_defense_applied"] is True
