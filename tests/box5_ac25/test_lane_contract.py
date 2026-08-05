"""§5 레인 계약 시험 (§11)."""
from __future__ import annotations

import pytest
from ac25 import lane_contract as lc

BASE = "a" * 40
HEAD = "b" * 40
HEAD_TREE = "c" * 40
MERGE = "d" * 40
VERIFIER = "e" * 40


def test_scope_end_is_candidate_head():
    li = lc.build_candidate_lane(
        approved_base_commit=BASE, approved_head_commit=HEAD,
        approved_head_tree=HEAD_TREE, verifier_commit=VERIFIER)
    assert li.policy_scope_end == HEAD
    assert li.policy_scope_start == BASE
    assert li.execution_commit == HEAD  # candidate 실행 == 후보 head


def test_candidate_lane_exact_identity_passes():
    li = lc.build_candidate_lane(
        approved_base_commit=BASE, approved_head_commit=HEAD,
        approved_head_tree=HEAD_TREE, verifier_commit=VERIFIER)
    assert li.candidate_commit == HEAD and li.candidate_tree == HEAD_TREE


def test_integration_lane_with_candidate_scope_passes():
    li = lc.build_integration_lane(
        approved_base_commit=BASE, approved_head_commit=HEAD,
        approved_head_tree=HEAD_TREE, merge_commit=MERGE,
        merge_parents=(BASE, HEAD), merge_tree="f" * 40, verifier_commit=VERIFIER)
    # 실행은 병합 커밋이지만 정책 범위는 여전히 base..head
    assert li.execution_commit == MERGE
    assert li.policy_scope_start == BASE and li.policy_scope_end == HEAD


def test_merge_commit_is_never_policy_scope_end():
    # 병합 커밋이 후보 head 로 오면(잘못된 구성) 거부
    with pytest.raises(lc.LaneContractError) as e:
        lc.build_integration_lane(
            approved_base_commit=BASE, approved_head_commit=HEAD,
            approved_head_tree=HEAD_TREE, merge_commit=HEAD,  # == scope_end
            merge_parents=(BASE, HEAD), merge_tree="f" * 40, verifier_commit=VERIFIER)
    assert e.value.code == lc.LANE_MERGE_EQUALS_SCOPE_END


def test_integration_merge_must_have_candidate_parent():
    with pytest.raises(lc.LaneContractError) as e:
        lc.build_integration_lane(
            approved_base_commit=BASE, approved_head_commit=HEAD,
            approved_head_tree=HEAD_TREE, merge_commit=MERGE,
            merge_parents=(BASE, "9" * 40), merge_tree="f" * 40, verifier_commit=VERIFIER)
    assert e.value.code == lc.LANE_MERGE_PARENT_MISSING_CANDIDATE


@pytest.mark.parametrize("expr", [
    "github.event.pull_request.head.sha", "github.sha",
    "lock.approved_head_commit", "${{ inputs.expected_head }}", "HEAD",
])
def test_expression_string_is_not_a_coordinate(expr):
    with pytest.raises(lc.LaneContractError) as e:
        lc.build_candidate_lane(
            approved_base_commit=BASE, approved_head_commit=expr,
            approved_head_tree=HEAD_TREE, verifier_commit=VERIFIER)
    assert e.value.code == lc.LANE_COORDINATE_NOT_OID
