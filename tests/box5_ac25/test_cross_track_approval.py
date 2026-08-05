"""§8 교차 트랙 승인서 시험 + §10 좌표 축 (§11)."""
from __future__ import annotations

import dataclasses
import hashlib

import pytest
from ac25 import cross_track_approval as cta

HEAD = "6" * 40
HEAD_TREE = "3" * 40
INT_BASE = "a" * 40          # 통합 비교 base
POLICY_BASE = "d" * 40       # 경로 판정 base (섞지 않음)
DOC = b"approval document bytes"
DOC_SHA = hashlib.sha256(DOC).hexdigest()
PATHS = frozenset({"butler-desktop/src/lib/accounting_review/client.ts",
                   "butler-desktop/src/components/accounting_review/AccountingReviewPage.tsx"})

ANCHOR = cta.TrustAnchor(
    source_repo="ct/shared", protected_ref="refs/heads/main",
    document_path="doc.md", allowed_approver_ids=frozenset({238947383}),
    protected_ref_enforced=True)
COORD = cta.ApprovalCoordinates(
    candidate_head_sha=HEAD, candidate_head_tree=HEAD_TREE,
    integration_comparison_base=INT_BASE)


def _approval(**over):
    base = dict(
        schema_version="butler.ac25.cross_track_approval.v1",
        source_repo="ct/shared", protected_ref="refs/heads/main",
        approval_commit_sha="9" * 40, document_path="doc.md",
        document_sha256=DOC_SHA, approver_login="rep", approver_id=238947383,
        base_sha=INT_BASE, base_tree="b" * 40, head_sha=HEAD, head_tree=HEAD_TREE,
        approved_paths=PATHS, issued_at="2026-08-05T01:00:00Z",
        expires_at="2026-08-12T00:00:00Z")
    base.update(over)
    return cta.CrossTrackApproval(**base)


def _run(approval, protected=PATHS, doc=DOC, reachable=True,
         run_started="2026-08-05T02:00:00Z", now="2026-08-05T03:00:00Z", anchor=ANCHOR):
    return cta.verify_cross_track_approval(
        approval=approval, anchor=anchor, coordinates=COORD,
        protected_changed_paths=protected, document_bytes=doc,
        approval_commit_reachable=reachable, run_started_at=run_started, now=now)


def _codes(res):
    return {f.code for f in res[1]}


def test_valid_exact_approval_passes():
    ok, failures = _run(_approval())
    assert ok, failures


def test_missing_approval_is_rejected():
    ok, f = _run(None)
    assert not ok and cta.CROSS_TRACK_APPROVAL_NOT_FOUND in {x.code for x in f}


def test_trust_anchor_not_supplied_is_rejected():
    bad = dataclasses.replace(ANCHOR, allowed_approver_ids=frozenset())
    ok, f = _run(_approval(), anchor=bad)
    assert cta.APPROVAL_TRUST_ANCHOR_NOT_SUPPLIED in {x.code for x in f}


def test_protected_ref_not_enforced_is_rejected():
    bad = dataclasses.replace(ANCHOR, protected_ref_enforced=False)
    ok, f = _run(_approval(), anchor=bad)
    assert cta.APPROVAL_PROTECTED_REF_NOT_ENFORCED in {x.code for x in f}


def test_approval_digest_mismatch_is_rejected():
    assert cta.APPROVAL_DIGEST_MISMATCH in _codes(_run(_approval(document_sha256="0" * 64)))


def test_approval_wrong_repository_is_rejected():
    assert cta.APPROVAL_SOURCE_REPOSITORY_MISMATCH in _codes(_run(_approval(source_repo="evil/x")))


def test_approval_commit_not_reachable_is_rejected():
    assert cta.APPROVAL_COMMIT_NOT_REACHABLE in _codes(_run(_approval(), reachable=False))


def test_untrusted_approver_is_rejected():
    assert cta.APPROVAL_SIGNER_UNTRUSTED in _codes(_run(_approval(approver_id=999)))


def test_approval_pathset_extra_path_is_rejected():
    extra = PATHS | {"butler-desktop/src/lib/accounting_review/contracts.ts"}
    assert cta.APPROVAL_PATHSET_MISMATCH in _codes(_run(_approval(), protected=extra))


def test_approval_pathset_missing_path_is_rejected():
    fewer = frozenset(list(PATHS)[:1])
    assert cta.APPROVAL_PATHSET_MISMATCH in _codes(_run(_approval(), protected=fewer))


def test_approval_issued_after_run_is_rejected():
    assert cta.APPROVAL_ISSUED_AFTER_RUN in _codes(
        _run(_approval(issued_at="2026-08-05T05:00:00Z")))


def test_approval_not_yet_valid_is_rejected():
    # issued 미래, run/now 도 그 이전 → not yet valid (또는 issued_after_run)
    res = _run(_approval(issued_at="2026-08-10T00:00:00Z"),
               run_started="2026-08-06T00:00:00Z", now="2026-08-06T01:00:00Z")
    assert cta.APPROVAL_NOT_YET_VALID in _codes(res) or cta.APPROVAL_ISSUED_AFTER_RUN in _codes(res)


def test_expired_approval_is_rejected():
    res = _run(_approval(), run_started="2026-08-13T00:00:00Z", now="2026-08-13T01:00:00Z")
    assert cta.APPROVAL_EXPIRED in _codes(res)


def test_old_approval_cannot_be_replayed_for_new_head():
    # 승인은 옛 head 를 지목하지만 현재 후보 head 는 다름 → 좌표 불일치
    res = _run(_approval(head_sha="7" * 40))
    assert cta.APPROVAL_COORDINATE_MISMATCH in _codes(res)


# ── §10: 두 base 를 섞지 않는다 ────────────────────────────────────────
def test_base_axis_is_integration_base_not_policy_base():
    # 승인서 base 가 통합 비교 base 와 같으면(정책 base 와 달라도) 통과
    ok, f = _run(_approval(base_sha=INT_BASE))
    assert ok, f


def test_wrong_integration_base_is_rejected():
    res = _run(_approval(base_sha="1" * 40))
    assert cta.APPROVAL_COORDINATE_MISMATCH in _codes(res)
