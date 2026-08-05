"""§8 교차 트랙 승인서 계약 (승인 문서 §10 좌표 축 반영).

좌표 매칭 축 = candidate_head_sha 와 candidate_head_tree (승인 문서 §10).
불변식: 통합 비교 base 와 경로 판정 base 는 서로 섞지 않는다.
  · 승인서 base_sha 는 integration lane 의 비교 base 로만 대조한다.
  · 잠금 base(approved_base_commit) 는 경로 판정에만 쓴다.
  · 두 base 가 서로 같기를 요구하지 않는다.
근거: butler-ct-shared 교차트랙승인 문서 §10 (좌표 축 명시, 2026-08-05).

approver 문자열이나 document_sha256 만으로 승인을 인정하지 않는다.
승인 부재·API 실패·시각 파싱 실패는 모두 fail-closed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

# ── 실패 코드 (§8) ─────────────────────────────────────────────────────
CROSS_TRACK_APPROVAL_NOT_FOUND = "CROSS_TRACK_APPROVAL_NOT_FOUND"
APPROVAL_TRUST_ANCHOR_NOT_SUPPLIED = "APPROVAL_TRUST_ANCHOR_NOT_SUPPLIED"
APPROVAL_SOURCE_REPOSITORY_MISMATCH = "APPROVAL_SOURCE_REPOSITORY_MISMATCH"
APPROVAL_PROTECTED_REF_MISMATCH = "APPROVAL_PROTECTED_REF_MISMATCH"
APPROVAL_PROTECTED_REF_NOT_ENFORCED = "APPROVAL_PROTECTED_REF_NOT_ENFORCED"
APPROVAL_COMMIT_NOT_REACHABLE = "APPROVAL_COMMIT_NOT_REACHABLE"
APPROVAL_SIGNER_UNTRUSTED = "APPROVAL_SIGNER_UNTRUSTED"
APPROVAL_DIGEST_MISMATCH = "APPROVAL_DIGEST_MISMATCH"
APPROVAL_COORDINATE_MISMATCH = "APPROVAL_COORDINATE_MISMATCH"
APPROVAL_PATHSET_MISMATCH = "APPROVAL_PATHSET_MISMATCH"
APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
APPROVAL_NOT_YET_VALID = "APPROVAL_NOT_YET_VALID"
APPROVAL_ISSUED_AFTER_RUN = "APPROVAL_ISSUED_AFTER_RUN"
APPROVAL_TIME_INVALID = "APPROVAL_TIME_INVALID"

_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ApprovalFailure:
    code: str
    message: str
    expected: str | None = None
    observed: str | None = None


@dataclass(frozen=True)
class TrustAnchor:
    """보호된 설정에서 고정하는 네 신뢰원(§8) + 허용 승인자."""
    source_repo: str
    protected_ref: str
    document_path: str
    allowed_approver_ids: frozenset[int]
    protected_ref_enforced: bool  # 되감기·삭제 금지가 실측으로 확인됐는가


@dataclass(frozen=True)
class CrossTrackApproval:
    schema_version: str
    source_repo: str
    protected_ref: str
    approval_commit_sha: str
    document_path: str
    document_sha256: str
    approver_login: str
    approver_id: int
    base_sha: str
    base_tree: str
    head_sha: str
    head_tree: str
    approved_paths: frozenset[str]
    issued_at: str
    expires_at: str


def _parse_utc(value: str) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo == timezone.utc else None


@dataclass(frozen=True)
class ApprovalCoordinates:
    """잠금에서 온 후보 지목 좌표(§10 축) + 통합 비교 base(별도 축)."""
    candidate_head_sha: str      # == lock.approved_head_commit
    candidate_head_tree: str     # == lock.approved_head_tree
    integration_comparison_base: str  # PR 이벤트 base (afdb237e); 잠금 base 와 섞지 않음


def verify_cross_track_approval(
    *,
    approval: CrossTrackApproval | None,
    anchor: TrustAnchor,
    coordinates: ApprovalCoordinates,
    protected_changed_paths: frozenset[str],
    document_bytes: bytes | None,
    approval_commit_reachable: bool,
    run_started_at: str,
    now: str,
) -> tuple[bool, tuple[ApprovalFailure, ...]]:
    """승인서를 신뢰원 기준으로 검증. (ok, failures) 반환. 부재/실패는 fail-closed."""
    f: list[ApprovalFailure] = []

    # 신뢰원 자체가 공급/집행되지 않으면 즉시 닫는다
    if not (anchor.source_repo and anchor.protected_ref and anchor.document_path
            and anchor.allowed_approver_ids):
        return False, (ApprovalFailure(APPROVAL_TRUST_ANCHOR_NOT_SUPPLIED, "승인 신뢰원 네 값 미공급"),)
    if not anchor.protected_ref_enforced:
        return False, (ApprovalFailure(
            APPROVAL_PROTECTED_REF_NOT_ENFORCED,
            "보호 ref 되감기·삭제 금지가 확인되지 않음"),)

    # 변경 경로가 있는데 승인서가 없으면 반드시 NOT_FOUND (§9)
    if approval is None:
        return False, (ApprovalFailure(CROSS_TRACK_APPROVAL_NOT_FOUND, "승인서 없음"),)

    if approval.source_repo != anchor.source_repo:
        f.append(ApprovalFailure(APPROVAL_SOURCE_REPOSITORY_MISMATCH, "승인 저장소 불일치",
                                 expected=anchor.source_repo, observed=approval.source_repo))
    if approval.protected_ref != anchor.protected_ref:
        f.append(ApprovalFailure(APPROVAL_PROTECTED_REF_MISMATCH, "보호 ref 불일치",
                                 expected=anchor.protected_ref, observed=approval.protected_ref))
    if approval.document_path != anchor.document_path:
        f.append(ApprovalFailure(APPROVAL_PROTECTED_REF_MISMATCH, "승인 문서 경로 불일치",
                                 expected=anchor.document_path, observed=approval.document_path))
    if not _OID_RE.match(approval.approval_commit_sha):
        f.append(ApprovalFailure(APPROVAL_COMMIT_NOT_REACHABLE, "approval_commit_sha 형식 오류",
                                 observed=approval.approval_commit_sha))
    elif not approval_commit_reachable:
        f.append(ApprovalFailure(APPROVAL_COMMIT_NOT_REACHABLE, "승인 커밋이 보호 ref 에서 도달 불가",
                                 observed=approval.approval_commit_sha))

    # 서명자: 인증된 ID 로만 판정(이름 문자열 금지)
    if approval.approver_id not in anchor.allowed_approver_ids:
        f.append(ApprovalFailure(APPROVAL_SIGNER_UNTRUSTED, "승인자 ID 미허용",
                                 expected=str(sorted(anchor.allowed_approver_ids)),
                                 observed=str(approval.approver_id)))

    # 문서 digest 재계산 대조(이미 fetch 한 immutable 바이트만)
    if document_bytes is None:
        f.append(ApprovalFailure(APPROVAL_DIGEST_MISMATCH, "승인 문서 바이트 미확보"))
    else:
        got = hashlib.sha256(document_bytes).hexdigest()
        if not (_SHA256_RE.match(approval.document_sha256) and got == approval.document_sha256):
            f.append(ApprovalFailure(APPROVAL_DIGEST_MISMATCH, "문서 SHA-256 불일치",
                                     expected=approval.document_sha256, observed=got))

    # ── 좌표 매칭 축 = head_sha + head_tree (승인 문서 §10) ──
    # 두 base 는 섞지 않는다: 승인서 base 는 통합 비교 base 로만 대조.
    if approval.head_sha != coordinates.candidate_head_sha:
        f.append(ApprovalFailure(APPROVAL_COORDINATE_MISMATCH, "head_sha != 후보 head",
                                 expected=coordinates.candidate_head_sha, observed=approval.head_sha))
    if approval.head_tree != coordinates.candidate_head_tree:
        f.append(ApprovalFailure(APPROVAL_COORDINATE_MISMATCH, "head_tree != 후보 head tree",
                                 expected=coordinates.candidate_head_tree, observed=approval.head_tree))
    if approval.base_sha != coordinates.integration_comparison_base:
        f.append(ApprovalFailure(APPROVAL_COORDINATE_MISMATCH,
                                 "base_sha != 통합 비교 base(§10: 경로 base 와 섞지 않음)",
                                 expected=coordinates.integration_comparison_base,
                                 observed=approval.base_sha))

    # 경로 집합 완전일치(§16-3): 보호 범위로 거른 변경 == 승인 경로
    if approval.approved_paths != protected_changed_paths:
        extra = sorted(protected_changed_paths - approval.approved_paths)
        missing = sorted(approval.approved_paths - protected_changed_paths)
        f.append(ApprovalFailure(APPROVAL_PATHSET_MISMATCH,
                                 f"보호 변경경로 != 승인경로 (extra={extra} missing={missing})"))

    # 시각 순서(§8-10): issued_at <= run_started_at <= now <= expires_at
    issued = _parse_utc(approval.issued_at)
    expires = _parse_utc(approval.expires_at)
    rstart = _parse_utc(run_started_at)
    tnow = _parse_utc(now)
    if None in (issued, expires, rstart, tnow):
        f.append(ApprovalFailure(APPROVAL_TIME_INVALID, "시각 파싱 실패(UTC 필요)"))
    else:
        if issued > rstart:
            f.append(ApprovalFailure(APPROVAL_ISSUED_AFTER_RUN, "발행이 실행보다 늦음",
                                     expected=f"issued <= {run_started_at}", observed=approval.issued_at))
        if rstart > tnow:
            f.append(ApprovalFailure(APPROVAL_TIME_INVALID, "run_started_at > now"))
        if tnow > expires:
            f.append(ApprovalFailure(APPROVAL_EXPIRED, "승인 만료",
                                     expected=f"now <= {approval.expires_at}", observed=now))
        if tnow < issued:
            f.append(ApprovalFailure(APPROVAL_NOT_YET_VALID, "아직 유효하지 않음"))

    return (not f), tuple(f)
