"""§9 보호 범위 판정 + §16-3 정정 시험 (§11 + 부록) — 정오표 v1.2 (v2) 반영.

서명 검증이 필수가 됐으므로 통과 상태 시험도 실물 승인 산출물 픽스처를 쓴다.
좌표는 이 시험의 관심사가 아니라 합성값을 쓰되, 승인서·잠금·PR 이벤트에서 온
좌표가 서로 일치하도록 맞춘다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from ac25 import cross_track_approval as cta
from ac25 import protected_scope as ps
from ac25.approval_signature import SIGNATURE_NAMESPACE, SIGNING_KEY_FINGERPRINT

pytestmark = pytest.mark.no_sidecar_token

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DOC = (FIXTURES / "approval_document.md").read_bytes()
SIG = (FIXTURES / "approval_document.md.sig").read_bytes()
SIGNERS = (FIXTURES / "allowed_signers").read_bytes()
DOC_SHA = hashlib.sha256(DOC).hexdigest()

HEAD = "6" * 40
HEAD_TREE = "3" * 40
INT_BASE = "a" * 40
PROV_BASE = "d" * 40
PROV_BASE_TREE = "b" * 40
ZIP_DIGEST = "5" * 64
MANIFEST_DIGEST = "b" * 64

P1 = "butler-desktop/src/lib/accounting_review/client.ts"
P2 = "butler-desktop/src/components/accounting_review/AccountingReviewPage.tsx"
UNPROT = "butler-desktop/src/lib/other/thing.ts"

ANCHOR = cta.TrustAnchor(
    source_repo="ct/shared",
    protected_ref="refs/heads/main",
    document_path="doc.md",
    signature_path="doc.md.sig",
    allowed_signers_path="allowed_signers",
)
COORD = cta.ApprovalCoordinates(
    candidate_head_sha=HEAD,
    candidate_head_tree=HEAD_TREE,
    provenance_base_sha=PROV_BASE,
    provenance_base_tree=PROV_BASE_TREE,
    integration_comparison_base=INT_BASE,
)
IDENTITY = cta.IdentityDigests(
    identity_artifact_zip_sha256=ZIP_DIGEST,
    identity_manifest_sha256=MANIFEST_DIGEST,
)

# ★건너뛰지 않는다. ssh-keygen 이 없으면 서명 검증을 못 한 것이고, 그것은
#   통과가 아니라 실패다(§E6-4 skipped=0). conftest 의 fixture 가 실패시킨다.
requires_ssh_keygen = pytest.mark.usefixtures("require_ssh_keygen")


def _approval(paths):
    return cta.CrossTrackApprovalV2(
        schema_version=cta.SCHEMA_VERSION,
        integration_base_sha=INT_BASE,
        provenance_base_sha=PROV_BASE,
        provenance_base_tree=PROV_BASE_TREE,
        candidate_head_sha=HEAD,
        candidate_head_tree=HEAD_TREE,
        identity_artifact_zip_sha256=ZIP_DIGEST,
        identity_manifest_sha256=MANIFEST_DIGEST,
        approved_paths=frozenset(paths),
        source_repo="ct/shared",
        protected_ref="refs/heads/main",
        document_path="doc.md",
        approval_commit_sha="9" * 40,
        document_sha256=DOC_SHA,
        approver_login="rep",
        approver_id=1,
        signature_path="doc.md.sig",
        allowed_signers_path="allowed_signers",
        signing_key_fingerprint=SIGNING_KEY_FINGERPRINT,
        signature_namespace=SIGNATURE_NAMESPACE,
        expires_at="2026-08-12T00:00:00Z",
    )


def _remote():
    return cta.RemoteFacts(
        approval_commit_fetchable=True,
        approval_commit_reachable=True,
        approval_committer_utc="2026-08-05T01:00:00Z",
        run_started_at="2026-08-05T02:00:00Z",
        document_bytes=DOC,
        signature_bytes=SIG,
        allowed_signers_bytes=SIGNERS,
        approver_id_for_login=1,
    )


def _eval(changed, approval, verified_unchanged=False):
    return ps.evaluate_protected_scope(
        changed_paths=frozenset(changed),
        verified_unchanged=verified_unchanged,
        approval=approval,
        anchor=ANCHOR,
        coordinates=COORD,
        identity=IDENTITY,
        remote=_remote(),
        now="2026-08-05T03:00:00Z",
    )


def test_is_protected_scope_boundary():
    assert ps.is_protected_scope(P1) and ps.is_protected_scope(P2)
    assert not ps.is_protected_scope(UNPROT)


def test_valid_unchanged_state_passes():
    # 보호 범위 변경 없음 + verified_unchanged → 상태1 통과
    verdict = _eval([UNPROT], approval=None, verified_unchanged=True)
    assert verdict.ok and verdict.state == "STATE_1_UNCHANGED"


def test_unprotected_path_does_not_require_approval():
    verdict = _eval([UNPROT, "README.md"], approval=None, verified_unchanged=True)
    assert verdict.ok


@requires_ssh_keygen
def test_valid_exact_approval_state_passes():
    verdict = _eval([P1, P2, UNPROT], approval=_approval([P1, P2]))
    assert verdict.failures == ()
    assert verdict.ok and verdict.state == "STATE_2_APPROVED"
    assert set(verdict.protected_changed_paths) == {P1, P2}


@requires_ssh_keygen
def test_protected_subset_is_compared_not_full_changeset():
    # 변경 3개(보호 2 + 비보호 1)인데 승인은 보호 2 만 → 통과(§16-3)
    verdict = _eval([P1, P2, UNPROT], approval=_approval([P1, P2]))
    assert verdict.ok  # 전체 3 이 아니라 보호 부분집합 2 와 비교


def test_extra_protected_path_outside_approval_is_rejected():
    verdict = _eval(
        [P1, P2, "butler-desktop/src/lib/accounting_review/contracts.ts"],
        approval=_approval([P1, P2]),
    )
    assert not verdict.ok
    assert any(f.code == cta.APPROVAL_PATHSET_MISMATCH for f in verdict.failures)


def test_missing_approval_with_protected_change_is_rejected():
    verdict = _eval([P1], approval=None)
    assert not verdict.ok
    assert any(f.code == cta.CROSS_TRACK_APPROVAL_NOT_FOUND for f in verdict.failures)


def test_empty_protected_change_without_verification_is_rejected():
    verdict = _eval([UNPROT], approval=None, verified_unchanged=False)
    assert not verdict.ok
    assert any(f.code == ps.PROTECTED_SCOPE_EMPTY_STATE_INVALID for f in verdict.failures)
