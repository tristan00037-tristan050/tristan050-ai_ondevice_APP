from __future__ import annotations

from butler_pc_core.cards.box3.actual_fail_class import (
    BLOCKED,
    FAIL_CLASS_SEVERITY,
    NEEDS_REVIEW_EVIDENCE_CARD_META_ECHO,
    is_blocking_actual_fail_class,
)
from butler_pc_core.cards.box3.actual_operation_pipeline import (
    _is_evidence_card_meta_echo,
    _is_output_skeleton_echo,
    _status_from_gate,
)
from butler_pc_core.cards.box3.real_contracts import EvidenceUnit


class _EvidenceStub:
    def __init__(self, text: str):
        self.evidence_units_runtime = [
            EvidenceUnit(
                evidence_id="e1",
                evidence_digest="sha256:" + "c" * 64,
                source_digest="sha256:" + "d" * 64,
                kind="text",
                text_runtime_only=text,
            )
        ]


def test_evidence_card_meta_echo_detected_when_scaffolding_leaks():
    ev = _EvidenceStub("납품처는 서울시청이다.")
    draft = (
        "제목: 조달 보고\n"
        "배경: 보존할 문구: 납품처는 서울시청입니다.\n"
        "근거: 반드시 복사할 값: 서울시청\n"
        "확인필요: 바꿔쓰기 금지: 예"
    )
    assert _is_evidence_card_meta_echo(draft, ev) is True


def test_shortened_rewrite_meta_echo_is_detected_in_isolation():
    ev = _EvidenceStub("납품처는 서울시청이다.")
    draft = "확인필요: 바꿔쓰기: 예"
    assert _is_evidence_card_meta_echo(draft, ev) is True


def test_normal_draft_is_not_flagged_as_meta_echo():
    ev = _EvidenceStub("납품처는 서울시청이다.")
    normal = "핵심내용: 납품처는 서울시청입니다. (근거1)"
    assert _is_evidence_card_meta_echo(normal, ev) is False


def test_system_rule_period_form_is_not_flagged_no_false_positive():
    # SYSTEM 규칙3의 "…그대로 보존합니다. 바꿔쓰기 금지."(마침표형)는 마커가 아니다.
    ev = _EvidenceStub("납품처는 서울시청이다.")
    draft = "최종문안: 값을 그대로 보존합니다. 바꿔쓰기 금지."
    assert _is_evidence_card_meta_echo(draft, ev) is False


def test_marker_present_in_evidence_is_not_meta_echo():
    # 마커 문자열이 실제 근거에도 있으면 에코가 아니다(정상).
    ev = _EvidenceStub("문서에 '보존할 문구:' 라는 서식 안내가 포함되어 있다.")
    draft = "핵심내용: 보존할 문구: 서울시청"
    assert _is_evidence_card_meta_echo(draft, ev) is False


def test_meta_echo_and_skeleton_echo_are_independent_detectors():
    ev = _EvidenceStub("납품처는 서울시청이다.")
    meta_only = "확인필요: 바꿔쓰기 금지: 예"
    skeleton_only = "제목: 주제 정보 요약"
    assert _is_evidence_card_meta_echo(meta_only, ev) is True
    assert _is_output_skeleton_echo(meta_only, ev) is False
    assert _is_evidence_card_meta_echo(skeleton_only, ev) is False
    assert _is_output_skeleton_echo(skeleton_only, ev) is True


def test_meta_echo_downgrades_hardblock_to_needs_review_delivery():
    assert FAIL_CLASS_SEVERITY[NEEDS_REVIEW_EVIDENCE_CARD_META_ECHO] == "needs_review"
    assert is_blocking_actual_fail_class(NEEDS_REVIEW_EVIDENCE_CARD_META_ECHO) is False
    status, real_allowed, fail_class, _ = _status_from_gate(
        base_status="ASSET_INVENTORY_PASS",
        helper_fail=None,
        parse_fail=None,
        runner_ok=True,
        runner_fail=None,
        bridge_fail=NEEDS_REVIEW_EVIDENCE_CARD_META_ECHO,
        metrics=None,
        fixed_eval_pass=True,
        approval_allowed=True,
        approval_fail=None,
        test_only_runner=False,
    )
    assert status != BLOCKED
    assert fail_class == NEEDS_REVIEW_EVIDENCE_CARD_META_ECHO
