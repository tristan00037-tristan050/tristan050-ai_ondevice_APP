"""§9 보호 범위 판정 (+ §16-3 정정: 전체 변경이 아니라 보호 부분집합을 비교).

통과 상태는 정확히 둘.
  상태1: changed_paths == 빈 집합 AND verified_unchanged == True
  상태2: changed_paths != 빈 집합 AND 신뢰원 유효 승인 존재
         AND protected_changed_paths == approval.approved_paths (집합 완전일치)
         AND 승인 좌표가 lock 좌표와 head+tree 로 완전일치(§10)
         AND 시각 순서·만료 충족
나머지는 전부 실패. 승인 부재 + 변경 존재 → CROSS_TRACK_APPROVAL_NOT_FOUND.

보호 범위 = 첫화면 accounting_review 계열(승인 문서 2장이 지목한 여섯 경로가
이 범위의 부분집합이며, 92개 변경 중 이 범위로 거르면 정확히 그 여섯이다).
"""
from __future__ import annotations

from dataclasses import dataclass

from .cross_track_approval import (
    CROSS_TRACK_APPROVAL_NOT_FOUND,
    ApprovalCoordinates,
    ApprovalFailure,
    CrossTrackApproval,
    TrustAnchor,
    verify_cross_track_approval,
)

# 보호 범위 경로 접두(디렉터리 경계). 상위/하위집합·glob 확대 금지.
PROTECTED_PREFIXES = (
    "butler-desktop/src/components/accounting_review/",
    "butler-desktop/src/lib/accounting_review/",
)

PROTECTED_SCOPE_EMPTY_STATE_INVALID = "PROTECTED_SCOPE_EMPTY_STATE_INVALID"
PROTECTED_SCOPE_NO_PASS_STATE = "PROTECTED_SCOPE_NO_PASS_STATE"


def is_protected_scope(path: str) -> bool:
    return any(path.startswith(pfx) for pfx in PROTECTED_PREFIXES)


def protected_subset(changed_paths: frozenset[str]) -> frozenset[str]:
    return frozenset(p for p in changed_paths if is_protected_scope(p))


@dataclass(frozen=True)
class ApprovalVerdict:
    ok: bool
    state: str  # "STATE_1_UNCHANGED" | "STATE_2_APPROVED" | "FAIL"
    failures: tuple[ApprovalFailure, ...]
    protected_changed_paths: tuple[str, ...]


def evaluate_protected_scope(
    *,
    changed_paths: frozenset[str],
    verified_unchanged: bool,
    approval: CrossTrackApproval | None,
    anchor: TrustAnchor,
    coordinates: ApprovalCoordinates,
    document_bytes: bytes | None,
    approval_commit_reachable: bool,
    run_started_at: str,
    now: str,
) -> ApprovalVerdict:
    protected = protected_subset(changed_paths)

    # 상태1: 보호 범위 안에서 변경이 없음
    if not protected:
        if verified_unchanged:
            return ApprovalVerdict(True, "STATE_1_UNCHANGED", (), ())
        # 보호 변경 없음이 확인되지 않으면 통과로 처리하지 않는다
        return ApprovalVerdict(
            False, "FAIL",
            (ApprovalFailure(PROTECTED_SCOPE_EMPTY_STATE_INVALID,
                             "보호 변경 없음이 검증되지 않음(verified_unchanged=False)"),),
            ())

    # 보호 변경이 있는데 승인서가 없으면 반드시 NOT_FOUND
    if approval is None:
        return ApprovalVerdict(
            False, "FAIL",
            (ApprovalFailure(CROSS_TRACK_APPROVAL_NOT_FOUND, "보호 변경 존재하나 승인서 없음"),),
            tuple(sorted(protected)))

    # 상태2: 신뢰원 유효 승인 + 보호부분집합 == 승인경로(§16-3) + 좌표/시각
    ok, failures = verify_cross_track_approval(
        approval=approval, anchor=anchor, coordinates=coordinates,
        protected_changed_paths=protected,
        document_bytes=document_bytes,
        approval_commit_reachable=approval_commit_reachable,
        run_started_at=run_started_at, now=now,
    )
    if ok:
        return ApprovalVerdict(True, "STATE_2_APPROVED", (), tuple(sorted(protected)))
    return ApprovalVerdict(False, "FAIL", failures, tuple(sorted(protected)))
