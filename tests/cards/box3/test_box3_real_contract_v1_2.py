from __future__ import annotations

import json

import pytest

from butler_pc_core.cards.box3.real_contract import Box3RealRuntimeEnvelope
from butler_pc_core.cards.box3.security import Box3SecurityError, assert_no_raw_persistence, sha256_digest


def test_runtime_envelope_keeps_raw_out_of_repr_and_audit_seed():
    envelope = Box3RealRuntimeEnvelope.from_raw(
        request_text="프로젝트 알파 실행 초안을 작성합니다",
        reference_texts=["프로젝트 알파는 내부 검토를 완료했습니다."],
        company_format_text="제목, 배경, 핵심 내용, 근거, 확인 필요, 최종 문안 순서",
    )

    assert envelope.request_digest == sha256_digest("프로젝트 알파 실행 초안을 작성합니다")
    assert "프로젝트 알파 실행" not in repr(envelope)
    audit_seed = envelope.to_audit_seed()
    assert audit_seed["request_digest"].startswith("sha256:")
    assert "프로젝트 알파 실행" not in json.dumps(audit_seed, ensure_ascii=False)
    assert_no_raw_persistence(audit_seed)


def test_runtime_envelope_rejects_secrets_and_local_paths():
    with pytest.raises(Box3SecurityError):
        Box3RealRuntimeEnvelope.from_raw(
            request_text="sk-proj-a1234567890abcdef",
            reference_texts=["프로젝트 알파는 내부 검토를 완료했습니다."],
            company_format_text="제목, 배경, 핵심 내용",
        )

    with pytest.raises(Box3SecurityError):
        Box3RealRuntimeEnvelope.from_raw(
            request_text="프로젝트 알파 실행 초안",
            reference_texts=["/Users/person/Desktop/source.docx"],
            company_format_text="제목, 배경, 핵심 내용",
        )
