"""§E7-1 승인서 엄격 로더 시험.

★실물 승인 문서(butler-ct-shared f734960)를 그대로 읽어 통과시킨다.
  막기만 하는 로더가 아니라는 것을 이것으로 보인다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from ac25 import anchors
from ac25.approval_loader import (
    APPROVAL_DOCUMENT_MALFORMED,
    APPROVAL_DOCUMENT_TIME_DECLARED,
    ApprovalDocumentError,
    DocumentOrigin,
    load_approval_document,
)
from ac25.cross_track_approval import SCHEMA_VERSION

# ★R6-2 §5-1 — 좌표를 이 시험이 다시 적지 않는다. 보호된 단일 원본에서 읽는다.
from ac25 import stage_b_coordinates as _sbc  # noqa: E402

_COORDINATES = _sbc.load_trusted_coordinates()

pytestmark = pytest.mark.no_sidecar_token

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DOC = (FIXTURES / "approval_document.md").read_bytes()

ORIGIN = DocumentOrigin(
    repository=anchors.APPROVAL_REPOSITORY,
    protected_ref=anchors.APPROVAL_PROTECTED_REF,
    document_path=anchors.APPROVAL_DOCUMENT_PATH,
    approval_commit_sha=anchors.APPROVAL_COMMIT_SHA,
)


def _load(data: bytes):
    return load_approval_document(
        data, origin=ORIGIN, pinned_document_sha256=anchors.APPROVAL_DOCUMENT_SHA256
    )


def test_real_approval_document_loads():
    approval = _load(DOC)
    assert approval.schema_version == SCHEMA_VERSION
    assert approval.integration_base_sha == _COORDINATES.stage_b.integration_base
    assert approval.provenance_base_sha == _COORDINATES.provenance_base_commit
    assert approval.provenance_base_tree == _COORDINATES.provenance_base_tree
    assert approval.candidate_head_sha == _COORDINATES.stage_b.candidate_commit
    assert approval.candidate_head_tree == _COORDINATES.stage_b.candidate_tree
    assert approval.approver_login == "tristan00037-tristan050"
    assert approval.approver_id == 238947383
    assert approval.expires_at == "2026-08-12T23:59:59Z"
    assert approval.signature_namespace == "butler-approval"


def test_two_baselines_are_kept_in_separate_fields():
    approval = _load(DOC)
    assert approval.integration_base_sha != approval.provenance_base_sha


def test_exactly_six_approved_paths_are_read():
    approval = _load(DOC)
    assert len(approval.approved_paths) == 6
    assert all(path.startswith("butler-desktop/src/") for path in approval.approved_paths)
    # 산문 줄이 경로로 섞이지 않는다
    assert not any(" " in path for path in approval.approved_paths)


def test_pinned_digest_is_used_not_a_self_declared_one():
    """문서가 자기 지문을 선언해도 로더는 고정 지문만 쓴다(자기증명 차단)."""
    forged = DOC + b"\ndocument_sha256 " + b"9" * 64 + b"\n"
    approval = _load(forged)
    assert approval.document_sha256 == anchors.APPROVAL_DOCUMENT_SHA256


def test_origin_fields_come_from_where_bytes_were_fetched():
    other = DocumentOrigin(
        repository="attacker/repo",
        protected_ref="refs/heads/evil",
        document_path="evil.md",
        approval_commit_sha="0" * 40,
    )
    approval = load_approval_document(
        DOC, origin=other, pinned_document_sha256=anchors.APPROVAL_DOCUMENT_SHA256
    )
    # 신뢰원 대조는 상위(verify_cross_track_approval)에서 닫는다.
    # 로더는 측정값을 그대로 실어 보내야 그 대조가 뜻을 갖는다.
    assert approval.source_repo == "attacker/repo"
    assert approval.protected_ref == "refs/heads/evil"


# ── §E3 시각 ───────────────────────────────────────────────────────────
def test_document_declaring_issued_at_time_is_rejected():
    forged = DOC.replace(
        "issued_at   이 문서를".encode(),
        "issued_at   2026-08-05T00:00:00Z\nissued_at2  이 문서를".encode(),
    )
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(forged)
    assert caught.value.code == APPROVAL_DOCUMENT_TIME_DECLARED


def test_issued_at_is_never_a_field_on_the_approval():
    approval = _load(DOC)
    assert not hasattr(approval, "issued_at")


# ── 엄격성 ─────────────────────────────────────────────────────────────
def test_empty_document_is_rejected():
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(b"")
    assert caught.value.code == APPROVAL_DOCUMENT_MALFORMED


def test_non_utf8_document_is_rejected():
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(b"\xff\xfe not utf-8")
    assert caught.value.code == APPROVAL_DOCUMENT_MALFORMED


def test_duplicate_key_is_rejected():
    forged = DOC + b"\nexpires_at  2030-01-01T00:00:00Z\n"
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(forged)
    assert caught.value.code == APPROVAL_DOCUMENT_MALFORMED
    assert "expires_at" in caught.value.message


def test_missing_required_key_is_rejected():
    forged = DOC.replace("candidate_head_tree ".encode(), "candidate_head_tre_ ".encode())
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(forged)
    assert caught.value.code == APPROVAL_DOCUMENT_MALFORMED
    assert "candidate_head_tree" in caught.value.message


def test_malformed_oid_is_rejected():
    forged = DOC.replace(
        _COORDINATES.stage_b.candidate_commit.encode("ascii"), b"61ba1bf4"
    )
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(forged)
    assert caught.value.code == APPROVAL_DOCUMENT_MALFORMED


def test_non_utc_expiry_is_rejected():
    forged = DOC.replace(b"2026-08-12T23:59:59Z", b"2026-08-12T23:59:59+09:00")
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(forged)
    assert caught.value.code == APPROVAL_DOCUMENT_MALFORMED


def test_non_integer_approver_id_is_rejected():
    forged = DOC.replace(b"approver_id     238947383", b"approver_id     not-a-number")
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(forged)
    assert caught.value.code == APPROVAL_DOCUMENT_MALFORMED


def test_bad_fingerprint_shape_is_rejected():
    forged = DOC.replace(
        b"SHA256:q87ozBPt1b218/lngOptVPRfFpgblANbUuvlUbu8HL4", b"MD5:short"
    )
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(forged)
    assert caught.value.code == APPROVAL_DOCUMENT_MALFORMED


def test_document_without_path_section_is_rejected():
    forged = DOC.replace("## 3.".encode(), "## 33.".encode())
    with pytest.raises(ApprovalDocumentError) as caught:
        _load(forged)
    assert caught.value.code == APPROVAL_DOCUMENT_MALFORMED
