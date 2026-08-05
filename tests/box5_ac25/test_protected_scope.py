"""§9 보호 범위 판정 + §16-3 정정 시험 (§11 + 부록)."""
from __future__ import annotations

import hashlib

import pytest
from ac25 import cross_track_approval as cta
from ac25 import protected_scope as ps

HEAD = "6" * 40
HEAD_TREE = "3" * 40
INT_BASE = "a" * 40
DOC = b"doc"
DOC_SHA = hashlib.sha256(DOC).hexdigest()

P1 = "butler-desktop/src/lib/accounting_review/client.ts"
P2 = "butler-desktop/src/components/accounting_review/AccountingReviewPage.tsx"
UNPROT = "butler-desktop/src/lib/other/thing.ts"

ANCHOR = cta.TrustAnchor("ct/shared", "refs/heads/main", "doc.md",
                         frozenset({1}), protected_ref_enforced=True)
COORD = cta.ApprovalCoordinates(HEAD, HEAD_TREE, INT_BASE)


def _approval(paths):
    return cta.CrossTrackApproval(
        schema_version="butler.ac25.cross_track_approval.v1",
        source_repo="ct/shared", protected_ref="refs/heads/main",
        approval_commit_sha="9" * 40, document_path="doc.md",
        document_sha256=DOC_SHA, approver_login="rep", approver_id=1,
        base_sha=INT_BASE, base_tree="b" * 40, head_sha=HEAD, head_tree=HEAD_TREE,
        approved_paths=frozenset(paths),
        issued_at="2026-08-05T01:00:00Z", expires_at="2026-08-12T00:00:00Z")


def _eval(changed, approval, verified_unchanged=False):
    return ps.evaluate_protected_scope(
        changed_paths=frozenset(changed), verified_unchanged=verified_unchanged,
        approval=approval, anchor=ANCHOR, coordinates=COORD, document_bytes=DOC,
        approval_commit_reachable=True,
        run_started_at="2026-08-05T02:00:00Z", now="2026-08-05T03:00:00Z")


def test_is_protected_scope_boundary():
    assert ps.is_protected_scope(P1) and ps.is_protected_scope(P2)
    assert not ps.is_protected_scope(UNPROT)


def test_valid_unchanged_state_passes():
    # 보호 범위 변경 없음 + verified_unchanged → 상태1 통과
    v = _eval([UNPROT], approval=None, verified_unchanged=True)
    assert v.ok and v.state == "STATE_1_UNCHANGED"


def test_unprotected_path_does_not_require_approval():
    # 비보호 경로만 바뀌면 승인서가 없어도 상태1 통과(verified_unchanged)
    v = _eval([UNPROT, "README.md"], approval=None, verified_unchanged=True)
    assert v.ok


def test_valid_exact_approval_state_passes():
    v = _eval([P1, P2, UNPROT], approval=_approval([P1, P2]))
    assert v.ok and v.state == "STATE_2_APPROVED"
    assert set(v.protected_changed_paths) == {P1, P2}


def test_protected_subset_is_compared_not_full_changeset():
    # 변경 3개(보호 2 + 비보호 1)인데 승인은 보호 2 만 → 통과(§16-3)
    v = _eval([P1, P2, UNPROT], approval=_approval([P1, P2]))
    assert v.ok  # 전체 3 이 아니라 보호 부분집합 2 와 비교


def test_extra_protected_path_outside_approval_is_rejected():
    # 보호 변경 3개인데 승인은 2개만 → 초과 보호경로 fail-closed
    v = _eval([P1, P2, "butler-desktop/src/lib/accounting_review/contracts.ts"],
              approval=_approval([P1, P2]))
    assert not v.ok
    assert any(f.code == cta.APPROVAL_PATHSET_MISMATCH for f in v.failures)


def test_missing_approval_with_protected_change_is_rejected():
    v = _eval([P1], approval=None)
    assert not v.ok
    assert any(f.code == cta.CROSS_TRACK_APPROVAL_NOT_FOUND for f in v.failures)
