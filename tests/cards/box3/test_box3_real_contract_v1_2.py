"""융합 단일 계약 3객체 — from_raw 검증·digest-only 영속·audit 강제."""
from __future__ import annotations

import pytest

from butler_pc_core.cards.box3.real_contracts import (
    Box3RealRuntimeEnvelope,
    assert_audit_record_is_digest_only,
    build_audit_record,
)
from butler_pc_core.cards.box3.real_pipeline import run_box3_real_followup
from butler_pc_core.cards.box3.security import Box3SecurityError

from ._real_fusion_fixtures import passing_asset_manifest, passing_envelope, supported_runner


def test_from_raw_builds_runtime_only_envelope_with_digests():
    env = Box3RealRuntimeEnvelope.from_raw(
        drafting_request="요약 보고서를 작성하라",
        reference_texts=["프로젝트 알파는 2026년 3월 31일 납품 완료되었다."],
    )
    assert env.reference_digests and all(d.startswith("sha256:") for d in env.reference_digests)
    assert env.request_digest.startswith("sha256:")
    # 휘발 raw 는 repr 에 노출되지 않는다.
    assert "프로젝트" not in repr(env)


def test_from_raw_fails_closed_on_local_path_and_secret():
    with pytest.raises(Box3SecurityError):
        Box3RealRuntimeEnvelope.from_raw(
            drafting_request="요약",
            reference_texts=["참고 경로 /Users/secret/doc.docx 를 보라"],
        )
    with pytest.raises(Box3SecurityError):
        Box3RealRuntimeEnvelope.from_raw(
            drafting_request="api_key=sk-abcdefghijklmnopqrst 를 사용",
            reference_texts=["배경"],
        )


def test_post_init_rejects_invalid_max_new_tokens():
    with pytest.raises(ValueError):
        Box3RealRuntimeEnvelope(request_id="r", max_new_tokens=0)


def test_verdict_persistable_is_digest_only_and_suppresses_draft_text():
    verdict, audit = run_box3_real_followup(
        passing_envelope(), asset_manifest=passing_asset_manifest(), real_model_runner=supported_runner,
    )
    response = verdict.to_response_dict()
    persistable = verdict.to_persistable_dict()
    # 응답에는 draft_text 가 있으나 영속본에는 없다(digest only).
    assert "draft_text" in response
    assert "draft_text" not in persistable
    assert "request_id" not in persistable and persistable["request_digest"].startswith("sha256:")
    assert verdict.draft_digest and verdict.draft_digest.startswith("sha256:")


def test_audit_record_is_digest_only_enforced():
    verdict, audit = run_box3_real_followup(
        passing_envelope(), asset_manifest=passing_asset_manifest(), real_model_runner=supported_runner,
    )
    # raw/path/secret/PII 누출 0 — 예외 없이 통과.
    assert_audit_record_is_digest_only(audit)
    data = audit.to_dict()
    assert data["request_digest"].startswith("sha256:")
    assert all(d.startswith("sha256:") for d in data["reference_digests"])
    assert "draft_text" not in data
