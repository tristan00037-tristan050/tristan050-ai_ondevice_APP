"""§5 레인 계약.

CANDIDATE 레인과 INTEGRATION 레인의 좌표 불변식을 강제한다.
GitHub 표현식 이름(github.event...·github.sha·lock.approved_head_commit)을
좌표 값으로 저장하지 않는다 — 실제 40자 Git OID/64자 tree 만 저장한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Lane(str, Enum):
    CANDIDATE = "CANDIDATE"
    INTEGRATION = "INTEGRATION"


class LaneContractError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


LANE_EXECUTION_HEAD_MISMATCH = "LANE_EXECUTION_HEAD_MISMATCH"
LANE_EXECUTION_TREE_MISMATCH = "LANE_EXECUTION_TREE_MISMATCH"
LANE_SCOPE_START_INVALID = "LANE_SCOPE_START_INVALID"
LANE_SCOPE_END_INVALID = "LANE_SCOPE_END_INVALID"
LANE_MERGE_EQUALS_SCOPE_END = "LANE_MERGE_EQUALS_SCOPE_END"
LANE_MERGE_PARENT_MISSING_CANDIDATE = "LANE_MERGE_PARENT_MISSING_CANDIDATE"
LANE_COORDINATE_NOT_OID = "LANE_COORDINATE_NOT_OID"

_OID_RE = re.compile(r"^[0-9a-f]{40}$")
# 좌표로 저장하면 안 되는 GitHub 표현식/심볼 형태
_EXPRESSION_HINTS = ("github.", "inputs.", "lock.", "${{", "event.", "HEAD")


def _require_oid(field: str, value: str) -> None:
    if any(h in value for h in _EXPRESSION_HINTS) or not _OID_RE.match(value):
        raise LaneContractError(
            LANE_COORDINATE_NOT_OID,
            f"{field} 는 실제 40자 Git OID 여야 한다(표현식 문자열 금지): {value!r}",
        )


@dataclass(frozen=True)
class LaneIdentity:
    lane: Lane
    candidate_commit: str
    candidate_tree: str
    execution_commit: str
    execution_tree: str
    policy_scope_start: str
    policy_scope_end: str
    verifier_commit: str


def build_candidate_lane(
    *, approved_base_commit: str, approved_head_commit: str,
    approved_head_tree: str, verifier_commit: str,
) -> LaneIdentity:
    """CANDIDATE: execution == approved head, scope = base..head."""
    for f, v in (("approved_base_commit", approved_base_commit),
                 ("approved_head_commit", approved_head_commit),
                 ("verifier_commit", verifier_commit)):
        _require_oid(f, v)
    return _validated(LaneIdentity(
        lane=Lane.CANDIDATE,
        candidate_commit=approved_head_commit,
        candidate_tree=approved_head_tree,
        execution_commit=approved_head_commit,
        execution_tree=approved_head_tree,
        policy_scope_start=approved_base_commit,
        policy_scope_end=approved_head_commit,
        verifier_commit=verifier_commit,
    ), approved_head_commit=approved_head_commit,
        approved_head_tree=approved_head_tree)


def build_integration_lane(
    *, approved_base_commit: str, approved_head_commit: str,
    approved_head_tree: str, merge_commit: str, merge_parents: tuple[str, ...],
    merge_tree: str, verifier_commit: str,
) -> LaneIdentity:
    """INTEGRATION: execution == 실측 refs/pull/903/merge, scope 는 여전히 base..head."""
    for f, v in (("approved_base_commit", approved_base_commit),
                 ("approved_head_commit", approved_head_commit),
                 ("merge_commit", merge_commit), ("verifier_commit", verifier_commit)):
        _require_oid(f, v)
    if merge_commit == approved_head_commit:
        raise LaneContractError(
            LANE_MERGE_EQUALS_SCOPE_END,
            "합성 병합 커밋을 정책 scope_end 로 쓸 수 없다")
    if approved_head_commit not in merge_parents:
        raise LaneContractError(
            LANE_MERGE_PARENT_MISSING_CANDIDATE,
            f"합성 병합 부모에 후보 head({approved_head_commit}) 부재: {merge_parents}")
    return _validated(LaneIdentity(
        lane=Lane.INTEGRATION,
        candidate_commit=approved_head_commit,
        candidate_tree=approved_head_tree,
        execution_commit=merge_commit,
        execution_tree=merge_tree,
        policy_scope_start=approved_base_commit,
        policy_scope_end=approved_head_commit,
        verifier_commit=verifier_commit,
    ), approved_head_commit=approved_head_commit,
        approved_head_tree=approved_head_tree)


def _validated(li: LaneIdentity, *, approved_head_commit: str,
               approved_head_tree: str) -> LaneIdentity:
    # 공통 불변식
    if li.policy_scope_end != approved_head_commit:
        raise LaneContractError(LANE_SCOPE_END_INVALID, "policy_scope_end 는 후보 head 여야 한다")
    if li.candidate_commit != approved_head_commit:
        raise LaneContractError(LANE_EXECUTION_HEAD_MISMATCH, "candidate_commit != 후보 head")
    if li.candidate_tree != approved_head_tree:
        raise LaneContractError(LANE_EXECUTION_TREE_MISMATCH, "candidate_tree != 후보 head tree")
    if li.lane is Lane.CANDIDATE:
        if li.execution_commit != approved_head_commit:
            raise LaneContractError(LANE_EXECUTION_HEAD_MISMATCH, "CANDIDATE execution != head")
        if li.execution_tree != approved_head_tree:
            raise LaneContractError(LANE_EXECUTION_TREE_MISMATCH, "CANDIDATE execution tree != head tree")
    return li
