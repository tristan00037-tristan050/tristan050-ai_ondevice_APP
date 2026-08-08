"""§8 교차 트랙 승인서 계약 — 정오표 v1.2 반영판 (v2).

정오표 v1.2 가 바꾼 것:
  §E2  두 기준선을 한 칸에 넣지 않는다. 세 필드로 분리한다.
       integration_base_sha  통합 비교 기준 (PR 이벤트 base)
       provenance_base_sha   경로를 판정하는 승인 기준 (잠금 base)
       provenance_base_tree
       두 base 가 서로 같기를 요구하지 않는다. 한 칸에 넣어 비교하면
       BASELINE_ROLE_MISMATCH 로 닫는다.
  §E3  issued_at 은 문서 본문 문자열이 아니라 승인 커밋의 committer 시각이다.
       run_started_at 은 workflow run API 값이다. 사용자 입력을 쓰지 않는다.
  §E4  승인 진위는 서명으로 판정한다. approval_signature 모듈이 담당하며
       지문은 그 모듈에 고정돼 있다.
  §E1  identity manifest 는 후보 Git tree 가 아니라 8차 정본 결과물 ZIP 의
       구성 파일이다. 두 지문(zip·manifest)을 모두 확인한다. 하나만 맞으면
       통과시키지 않는다.

판정 경로에 assert 를 쓰지 않는다(§E6-2). 승인 부재·API 실패·시각 파싱 실패는
모두 fail-closed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .approval_signature import (
    APPROVAL_SIGNATURE_INVALID,
    APPROVAL_SIGNER_UNTRUSTED,
    SIGNATURE_NAMESPACE,
    SIGNING_KEY_FINGERPRINT,
    SignatureFailure,
    verify_approval_signature,
)

# ── 실패 코드 (§8 기존) ────────────────────────────────────────────────
CROSS_TRACK_APPROVAL_NOT_FOUND = "CROSS_TRACK_APPROVAL_NOT_FOUND"
APPROVAL_TRUST_ANCHOR_NOT_SUPPLIED = "APPROVAL_TRUST_ANCHOR_NOT_SUPPLIED"
APPROVAL_SOURCE_REPOSITORY_MISMATCH = "APPROVAL_SOURCE_REPOSITORY_MISMATCH"
APPROVAL_PROTECTED_REF_MISMATCH = "APPROVAL_PROTECTED_REF_MISMATCH"
APPROVAL_COMMIT_NOT_REACHABLE = "APPROVAL_COMMIT_NOT_REACHABLE"
APPROVAL_DIGEST_MISMATCH = "APPROVAL_DIGEST_MISMATCH"
APPROVAL_COORDINATE_MISMATCH = "APPROVAL_COORDINATE_MISMATCH"
APPROVAL_PATHSET_MISMATCH = "APPROVAL_PATHSET_MISMATCH"
APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
APPROVAL_NOT_YET_VALID = "APPROVAL_NOT_YET_VALID"
APPROVAL_ISSUED_AFTER_RUN = "APPROVAL_ISSUED_AFTER_RUN"
APPROVAL_TIME_INVALID = "APPROVAL_TIME_INVALID"

# ── 실패 코드 (§E5 추가 여섯) ──────────────────────────────────────────
IDENTITY_MANIFEST_NOT_FOUND = "IDENTITY_MANIFEST_NOT_FOUND"
IDENTITY_PACKAGE_DIGEST_MISMATCH = "IDENTITY_PACKAGE_DIGEST_MISMATCH"
BASELINE_ROLE_MISMATCH = "BASELINE_ROLE_MISMATCH"
APPROVAL_COMMIT_NOT_FETCHABLE = "APPROVAL_COMMIT_NOT_FETCHABLE"
# APPROVAL_SIGNATURE_INVALID · APPROVAL_SIGNER_UNTRUSTED 는 approval_signature 제공

SCHEMA_VERSION = "butler.ac25.cross_track_approval.v2"

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
    """보호된 설정에서 고정하는 신뢰원(§8·§E4)."""
    source_repo: str
    protected_ref: str
    document_path: str
    signature_path: str
    allowed_signers_path: str


@dataclass(frozen=True)
class CrossTrackApprovalV2:
    """§E2 정정 구조. 두 기준선을 한 칸에 넣지 않는다."""
    schema_version: str

    integration_base_sha: str
    provenance_base_sha: str
    provenance_base_tree: str

    candidate_head_sha: str
    candidate_head_tree: str

    identity_artifact_zip_sha256: str
    identity_manifest_sha256: str

    approved_paths: frozenset[str]

    source_repo: str
    protected_ref: str
    document_path: str
    approval_commit_sha: str
    document_sha256: str

    approver_login: str
    approver_id: int

    signature_path: str
    allowed_signers_path: str
    signing_key_fingerprint: str
    signature_namespace: str

    expires_at: str


@dataclass(frozen=True)
class ApprovalCoordinates:
    """잠금·PR 이벤트에서 온 좌표. 두 base 의 역할을 분리해 담는다."""
    candidate_head_sha: str           # lock.approved_head_commit
    candidate_head_tree: str          # lock.approved_head_tree
    provenance_base_sha: str          # lock.approved_base_commit
    provenance_base_tree: str         # lock.approved_base_tree
    integration_comparison_base: str  # PR 이벤트 base. 잠금 base 와 섞지 않는다.


@dataclass(frozen=True)
class IdentityDigests:
    """§E1 잠금에 고정한 두 지문. 둘 다 맞아야 한다."""
    identity_artifact_zip_sha256: str
    identity_manifest_sha256: str


@dataclass(frozen=True)
class RemoteFacts:
    """§E3 §E6-1 원격에서 그 자리에 다시 읽은 사실."""
    approval_commit_fetchable: bool
    approval_commit_reachable: bool
    approval_committer_utc: str        # issued_at 정본. 문서 본문 문자열이 아니다.
    run_started_at: str                # workflow run API 값
    document_bytes: bytes | None
    signature_bytes: bytes | None
    allowed_signers_bytes: bytes | None
    approver_id_for_login: int | None  # login 으로 조회한 실제 계정 ID


def _parse_utc(value: str) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo == timezone.utc else None


def _from_signature_failure(failure: SignatureFailure) -> ApprovalFailure:
    return ApprovalFailure(
        failure.code, failure.message, expected=failure.expected, observed=failure.observed
    )


def verify_cross_track_approval(
    *,
    approval: CrossTrackApprovalV2 | None,
    anchor: TrustAnchor,
    coordinates: ApprovalCoordinates,
    identity: IdentityDigests,
    protected_changed_paths: frozenset[str],
    remote: RemoteFacts,
    now: str,
) -> tuple[bool, tuple[ApprovalFailure, ...]]:
    """승인서를 신뢰원 기준으로 검증한다. (ok, failures)."""
    failures: list[ApprovalFailure] = []

    if not (
        anchor.source_repo
        and anchor.protected_ref
        and anchor.document_path
        and anchor.signature_path
        and anchor.allowed_signers_path
    ):
        return False, (
            ApprovalFailure(
                APPROVAL_TRUST_ANCHOR_NOT_SUPPLIED,
                "승인 신뢰원 값 미공급",
                expected="source_repo·protected_ref·document_path·signature_path·allowed_signers_path",
                observed="일부 비어 있음",
            ),
        )

    if approval is None:
        return False, (
            ApprovalFailure(
                CROSS_TRACK_APPROVAL_NOT_FOUND,
                "승인서 없음",
                expected=anchor.document_path,
                observed="없음",
            ),
        )

    if approval.schema_version != SCHEMA_VERSION:
        failures.append(
            ApprovalFailure(
                APPROVAL_COORDINATE_MISMATCH,
                "승인서 schema_version 불일치",
                expected=SCHEMA_VERSION,
                observed=str(approval.schema_version),
            )
        )

    # ── 신뢰원 좌표 ────────────────────────────────────────────────────
    if approval.source_repo != anchor.source_repo:
        failures.append(
            ApprovalFailure(
                APPROVAL_SOURCE_REPOSITORY_MISMATCH,
                "승인 저장소 불일치",
                expected=anchor.source_repo,
                observed=approval.source_repo,
            )
        )
    if approval.protected_ref != anchor.protected_ref:
        failures.append(
            ApprovalFailure(
                APPROVAL_PROTECTED_REF_MISMATCH,
                "보호 ref 불일치",
                expected=anchor.protected_ref,
                observed=approval.protected_ref,
            )
        )
    if approval.document_path != anchor.document_path:
        failures.append(
            ApprovalFailure(
                APPROVAL_PROTECTED_REF_MISMATCH,
                "승인 문서 경로 불일치",
                expected=anchor.document_path,
                observed=approval.document_path,
            )
        )

    # ── 승인 커밋 (§E5 NOT_FETCHABLE 분리) ────────────────────────────
    if not _OID_RE.match(approval.approval_commit_sha):
        failures.append(
            ApprovalFailure(
                APPROVAL_COMMIT_NOT_REACHABLE,
                "approval_commit_sha 형식 오류",
                expected="40자 소문자 Git OID",
                observed=approval.approval_commit_sha,
            )
        )
    elif not remote.approval_commit_fetchable:
        failures.append(
            ApprovalFailure(
                APPROVAL_COMMIT_NOT_FETCHABLE,
                "승인 커밋을 승인 저장소에서 가져오지 못했다",
                expected=approval.approval_commit_sha,
                observed="fetch 실패",
            )
        )
    elif not remote.approval_commit_reachable:
        failures.append(
            ApprovalFailure(
                APPROVAL_COMMIT_NOT_REACHABLE,
                "승인 커밋이 보호 ref 에서 도달 불가",
                expected=f"{anchor.protected_ref} 에서 도달 가능",
                observed=approval.approval_commit_sha,
            )
        )

    # ── §E4 서명 검증 ─────────────────────────────────────────────────
    if (
        remote.document_bytes is None
        or remote.signature_bytes is None
        or remote.allowed_signers_bytes is None
    ):
        failures.append(
            ApprovalFailure(
                APPROVAL_SIGNATURE_INVALID,
                "문서·서명·allowed_signers 바이트 미확보",
                expected="세 파일의 원문 바이트",
                observed="일부 없음",
            )
        )
    else:
        signature_ok, signature_failures = verify_approval_signature(
            document_bytes=remote.document_bytes,
            signature_bytes=remote.signature_bytes,
            allowed_signers_bytes=remote.allowed_signers_bytes,
        )
        if not signature_ok:
            failures.extend(_from_signature_failure(item) for item in signature_failures)

    # 승인서가 선언한 지문·namespace 도 고정값과 같아야 한다
    if approval.signing_key_fingerprint != SIGNING_KEY_FINGERPRINT:
        failures.append(
            ApprovalFailure(
                APPROVAL_SIGNER_UNTRUSTED,
                "승인서가 선언한 서명 지문이 고정값과 다르다",
                expected=SIGNING_KEY_FINGERPRINT,
                observed=approval.signing_key_fingerprint,
            )
        )
    if approval.signature_namespace != SIGNATURE_NAMESPACE:
        failures.append(
            ApprovalFailure(
                APPROVAL_SIGNER_UNTRUSTED,
                "승인서가 선언한 namespace 가 고정값과 다르다",
                expected=SIGNATURE_NAMESPACE,
                observed=approval.signature_namespace,
            )
        )

    # 승인자 ID 는 login 으로 조회한 실계정 ID 와 대조한다 (§E6-1)
    if remote.approver_id_for_login is None:
        failures.append(
            ApprovalFailure(
                APPROVAL_SIGNER_UNTRUSTED,
                "승인자 계정 ID 를 원격에서 확인하지 못했다",
                expected=str(approval.approver_id),
                observed="조회 실패",
            )
        )
    elif remote.approver_id_for_login != approval.approver_id:
        failures.append(
            ApprovalFailure(
                APPROVAL_SIGNER_UNTRUSTED,
                "승인자 ID 가 실계정과 다르다",
                expected=str(remote.approver_id_for_login),
                observed=str(approval.approver_id),
            )
        )

    # ── 문서 digest 재계산 ────────────────────────────────────────────
    if remote.document_bytes is None:
        failures.append(
            ApprovalFailure(
                APPROVAL_DIGEST_MISMATCH,
                "승인 문서 바이트 미확보",
                expected=approval.document_sha256,
                observed="바이트 없음",
            )
        )
    else:
        measured = hashlib.sha256(remote.document_bytes).hexdigest()
        if not _SHA256_RE.match(approval.document_sha256) or measured != approval.document_sha256:
            failures.append(
                ApprovalFailure(
                    APPROVAL_DIGEST_MISMATCH,
                    "문서 SHA-256 불일치",
                    expected=approval.document_sha256,
                    observed=measured,
                )
            )

    # ── §E1 identity 두 지문 (둘 다 맞아야 한다) ───────────────────────
    if not identity.identity_manifest_sha256 or not identity.identity_artifact_zip_sha256:
        failures.append(
            ApprovalFailure(
                IDENTITY_MANIFEST_NOT_FOUND,
                "잠금에 identity 지문이 없다",
                expected="zip·manifest 두 지문",
                observed="누락",
            )
        )
    else:
        if approval.identity_manifest_sha256 != identity.identity_manifest_sha256:
            failures.append(
                ApprovalFailure(
                    IDENTITY_PACKAGE_DIGEST_MISMATCH,
                    "identity manifest 지문 불일치",
                    expected=identity.identity_manifest_sha256,
                    observed=approval.identity_manifest_sha256,
                )
            )
        if approval.identity_artifact_zip_sha256 != identity.identity_artifact_zip_sha256:
            failures.append(
                ApprovalFailure(
                    IDENTITY_PACKAGE_DIGEST_MISMATCH,
                    "identity 결과물 ZIP 지문 불일치",
                    expected=identity.identity_artifact_zip_sha256,
                    observed=approval.identity_artifact_zip_sha256,
                )
            )

    # ── §E2 세 기준선 역할 대조 ───────────────────────────────────────
    if approval.candidate_head_sha != coordinates.candidate_head_sha:
        failures.append(
            ApprovalFailure(
                APPROVAL_COORDINATE_MISMATCH,
                "candidate_head_sha 불일치",
                expected=coordinates.candidate_head_sha,
                observed=approval.candidate_head_sha,
            )
        )
    if approval.candidate_head_tree != coordinates.candidate_head_tree:
        failures.append(
            ApprovalFailure(
                APPROVAL_COORDINATE_MISMATCH,
                "candidate_head_tree 불일치",
                expected=coordinates.candidate_head_tree,
                observed=approval.candidate_head_tree,
            )
        )
    if approval.provenance_base_sha != coordinates.provenance_base_sha:
        failures.append(
            ApprovalFailure(
                APPROVAL_COORDINATE_MISMATCH,
                "provenance_base_sha != 잠금 approved_base_commit",
                expected=coordinates.provenance_base_sha,
                observed=approval.provenance_base_sha,
            )
        )
    if approval.provenance_base_tree != coordinates.provenance_base_tree:
        failures.append(
            ApprovalFailure(
                APPROVAL_COORDINATE_MISMATCH,
                "provenance_base_tree != 잠금 approved_base_tree",
                expected=coordinates.provenance_base_tree,
                observed=approval.provenance_base_tree,
            )
        )
    if approval.integration_base_sha != coordinates.integration_comparison_base:
        failures.append(
            ApprovalFailure(
                APPROVAL_COORDINATE_MISMATCH,
                "integration_base_sha != 통합 비교 base",
                expected=coordinates.integration_comparison_base,
                observed=approval.integration_base_sha,
            )
        )

    # 두 base 가 한 칸에 뭉개진 승인서는 역할 혼동으로 닫는다 (§E2)
    if (
        coordinates.provenance_base_sha != coordinates.integration_comparison_base
        and approval.integration_base_sha == approval.provenance_base_sha
    ):
        failures.append(
            ApprovalFailure(
                BASELINE_ROLE_MISMATCH,
                "두 기준선이 한 칸에 들어갔다(통합 base 와 경로 base 가 같은 값)",
                expected=(
                    f"integration={coordinates.integration_comparison_base} "
                    f"provenance={coordinates.provenance_base_sha}"
                ),
                observed=approval.integration_base_sha,
            )
        )

    # ── 경로 집합 완전일치 ────────────────────────────────────────────
    if approval.approved_paths != protected_changed_paths:
        extra = sorted(protected_changed_paths - approval.approved_paths)
        missing = sorted(approval.approved_paths - protected_changed_paths)
        failures.append(
            ApprovalFailure(
                APPROVAL_PATHSET_MISMATCH,
                "보호 변경경로 != 승인경로",
                expected=f"missing={missing}",
                observed=f"extra={extra}",
            )
        )

    # ── §E3 시각 ─────────────────────────────────────────────────────
    issued = _parse_utc(remote.approval_committer_utc)
    expires = _parse_utc(approval.expires_at)
    run_started = _parse_utc(remote.run_started_at)
    current = _parse_utc(now)
    if issued is None or expires is None or run_started is None or current is None:
        failures.append(
            ApprovalFailure(
                APPROVAL_TIME_INVALID,
                "시각 파싱 실패(UTC 필요)",
                expected="…Z 형식 UTC",
                observed=(
                    f"issued={remote.approval_committer_utc} expires={approval.expires_at} "
                    f"run_started={remote.run_started_at} now={now}"
                ),
            )
        )
    else:
        if issued > run_started:
            failures.append(
                ApprovalFailure(
                    APPROVAL_ISSUED_AFTER_RUN,
                    "발행이 실행보다 늦음",
                    expected=f"issued <= {remote.run_started_at}",
                    observed=remote.approval_committer_utc,
                )
            )
        if run_started > current:
            failures.append(
                ApprovalFailure(
                    APPROVAL_TIME_INVALID,
                    "run_started_at > now",
                    expected=f"run_started <= {now}",
                    observed=remote.run_started_at,
                )
            )
        if current > expires:
            failures.append(
                ApprovalFailure(
                    APPROVAL_EXPIRED,
                    "승인 만료",
                    expected=f"now <= {approval.expires_at}",
                    observed=now,
                )
            )
        if current < issued:
            failures.append(
                ApprovalFailure(
                    APPROVAL_NOT_YET_VALID,
                    "아직 유효하지 않음",
                    expected=f"now >= {remote.approval_committer_utc}",
                    observed=now,
                )
            )

    return (not failures), tuple(failures)
