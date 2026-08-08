"""§8 교차 트랙 승인서 시험 — 정오표 v1.2 (v2) 반영.

§E6-4 가 지정한 열 개를 포함한다. 마지막 항목(정상 통과)을 반드시 넣는다.
막기만 하는 판정기는 언제나 막는 도구이므로 통과로 보지 않는다.

정상 통과 시험은 ★실물 승인 산출물(butler-ct-shared f734960 의 문서·서명·
allowed_signers)을 픽스처로 쓴다. 지문이 코드에 고정돼 있어 시험용 열쇠로는
통과시킬 수 없고, 그래야 시험이 실제 신뢰원을 검증한다.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from ac25 import cross_track_approval as cta
from ac25.approval_signature import SIGNATURE_NAMESPACE, SIGNING_KEY_FINGERPRINT

# ★R6-2 §5-1 — 좌표를 이 시험이 다시 적지 않는다. 보호된 단일 원본에서 읽는다.
from ac25 import stage_b_coordinates as _sbc  # noqa: E402

_COORDINATES = _sbc.load_trusted_coordinates()

pytestmark = pytest.mark.no_sidecar_token

FIXTURES = Path(__file__).resolve().parent / "fixtures"
AC25_SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "ac25"

DOCUMENT_BYTES = (FIXTURES / "approval_document.md").read_bytes()
SIGNATURE_BYTES = (FIXTURES / "approval_document.md.sig").read_bytes()
ALLOWED_SIGNERS_BYTES = (FIXTURES / "allowed_signers").read_bytes()
DOCUMENT_SHA256 = hashlib.sha256(DOCUMENT_BYTES).hexdigest()

INTEGRATION_BASE = _COORDINATES.stage_b.integration_base
PROVENANCE_BASE = _COORDINATES.provenance_base_commit
PROVENANCE_BASE_TREE = _COORDINATES.provenance_base_tree
CANDIDATE_HEAD = _COORDINATES.stage_b.candidate_commit
CANDIDATE_HEAD_TREE = _COORDINATES.stage_b.candidate_tree
ZIP_DIGEST = "5ea7f4b5355be5f4fd96b922c87f4530ddf6625abbef22848c091b2c629e2629"
MANIFEST_DIGEST = "b59e4aacd0d3f9bdd9874c838901c1ba0506478cfb15123536e729f83b4c2e4f"

APPROVAL_COMMIT = "f73496000e10dc533c3af243c1c0fb1c4d70e080"
COMMITTER_UTC = "2026-08-05T04:48:43Z"
RUN_STARTED_AT = "2026-08-05T05:00:00Z"
NOW = "2026-08-05T06:00:00Z"
EXPIRES_AT = "2026-08-12T23:59:59Z"

APPROVED_PATHS = frozenset({"butler_pc_core/accounting/assignment/authorization.py"})

ANCHOR = cta.TrustAnchor(
    source_repo="tristan00037-tristan050/butler-ct-shared",
    protected_ref="refs/heads/main",
    document_path="docs/decisions/교차트랙승인_박스5_AC12_v2_20260805.md",
    signature_path="docs/decisions/교차트랙승인_박스5_AC12_v2_20260805.md.sig",
    allowed_signers_path="docs/decisions/allowed_signers",
)

COORDINATES = cta.ApprovalCoordinates(
    candidate_head_sha=CANDIDATE_HEAD,
    candidate_head_tree=CANDIDATE_HEAD_TREE,
    provenance_base_sha=PROVENANCE_BASE,
    provenance_base_tree=PROVENANCE_BASE_TREE,
    integration_comparison_base=INTEGRATION_BASE,
)

IDENTITY = cta.IdentityDigests(
    identity_artifact_zip_sha256=ZIP_DIGEST,
    identity_manifest_sha256=MANIFEST_DIGEST,
)


def _approval(**overrides) -> cta.CrossTrackApprovalV2:
    base = cta.CrossTrackApprovalV2(
        schema_version=cta.SCHEMA_VERSION,
        integration_base_sha=INTEGRATION_BASE,
        provenance_base_sha=PROVENANCE_BASE,
        provenance_base_tree=PROVENANCE_BASE_TREE,
        candidate_head_sha=CANDIDATE_HEAD,
        candidate_head_tree=CANDIDATE_HEAD_TREE,
        identity_artifact_zip_sha256=ZIP_DIGEST,
        identity_manifest_sha256=MANIFEST_DIGEST,
        approved_paths=APPROVED_PATHS,
        source_repo=ANCHOR.source_repo,
        protected_ref=ANCHOR.protected_ref,
        document_path=ANCHOR.document_path,
        approval_commit_sha=APPROVAL_COMMIT,
        document_sha256=DOCUMENT_SHA256,
        approver_login="tristan00037-tristan050",
        approver_id=238947383,
        signature_path=ANCHOR.signature_path,
        allowed_signers_path=ANCHOR.allowed_signers_path,
        signing_key_fingerprint=SIGNING_KEY_FINGERPRINT,
        signature_namespace=SIGNATURE_NAMESPACE,
        expires_at=EXPIRES_AT,
    )
    return dataclasses.replace(base, **overrides) if overrides else base


def _remote(**overrides) -> cta.RemoteFacts:
    base = cta.RemoteFacts(
        approval_commit_fetchable=True,
        approval_commit_reachable=True,
        approval_committer_utc=COMMITTER_UTC,
        run_started_at=RUN_STARTED_AT,
        document_bytes=DOCUMENT_BYTES,
        signature_bytes=SIGNATURE_BYTES,
        allowed_signers_bytes=ALLOWED_SIGNERS_BYTES,
        approver_id_for_login=238947383,
    )
    return dataclasses.replace(base, **overrides) if overrides else base


def _verify(approval=None, remote=None, identity=IDENTITY, paths=APPROVED_PATHS, now=NOW):
    return cta.verify_cross_track_approval(
        approval=_approval() if approval is None else approval,
        anchor=ANCHOR,
        coordinates=COORDINATES,
        identity=identity,
        protected_changed_paths=paths,
        remote=_remote() if remote is None else remote,
        now=now,
    )


def _codes(failures) -> set[str]:
    return {item.code for item in failures}


_SSH_KEYGEN = shutil.which("ssh-keygen")
# ★건너뛰지 않는다. ssh-keygen 이 없으면 서명 검증을 못 한 것이고, 그것은
#   통과가 아니라 실패다(§E6-4 skipped=0). conftest 의 fixture 가 실패시킨다.
requires_ssh_keygen = pytest.mark.usefixtures("require_ssh_keygen")


# ── §E6-4 지정 열 개 ──────────────────────────────────────────────────


def test_identity_zip_digest_mismatch_is_rejected():
    ok, failures = _verify(approval=_approval(identity_artifact_zip_sha256="0" * 64))
    assert ok is False
    assert cta.IDENTITY_PACKAGE_DIGEST_MISMATCH in _codes(failures)


def test_identity_manifest_digest_mismatch_is_rejected():
    ok, failures = _verify(approval=_approval(identity_manifest_sha256="0" * 64))
    assert ok is False
    assert cta.IDENTITY_PACKAGE_DIGEST_MISMATCH in _codes(failures)


def test_two_baselines_in_one_field_is_rejected():
    """통합 base 자리에 경로 base 를 넣어 한 칸으로 뭉갠 승인서는 닫는다."""
    ok, failures = _verify(approval=_approval(integration_base_sha=PROVENANCE_BASE))
    assert ok is False
    assert cta.BASELINE_ROLE_MISMATCH in _codes(failures)


def test_document_time_string_is_not_used_as_issued_at():
    """issued_at 은 커밋 committer 시각이다. 승인서 구조에 그 칸이 없어야 한다."""
    fields = {field.name for field in dataclasses.fields(cta.CrossTrackApprovalV2)}
    assert "issued_at" not in fields

    # 커밋 시각이 run 시작보다 늦으면 닫힌다 — 문서 본문 문자열로는 바꿀 수 없다.
    ok, failures = _verify(remote=_remote(approval_committer_utc="2026-08-05T05:30:00Z"))
    assert ok is False
    assert cta.APPROVAL_ISSUED_AFTER_RUN in _codes(failures)


@requires_ssh_keygen
def test_unsigned_approval_is_rejected():
    ok, failures = _verify(remote=_remote(signature_bytes=None))
    assert ok is False
    assert cta.APPROVAL_SIGNATURE_INVALID in _codes(failures)


@requires_ssh_keygen
def test_wrong_signer_key_is_rejected(tmp_path):
    """다른 열쇠로 만든 allowed_signers 는 고정 지문과 달라 거부된다."""
    key = tmp_path / "other"
    subprocess.run(
        [_SSH_KEYGEN, "-t", "ed25519", "-N", "", "-C", "other", "-f", str(key)],
        capture_output=True,
        check=True,
    )
    public = (tmp_path / "other.pub").read_text(encoding="utf-8").strip()
    other_signers = f'butler-approval-signer namespaces="butler-approval" {public}\n'
    ok, failures = _verify(remote=_remote(allowed_signers_bytes=other_signers.encode("utf-8")))
    assert ok is False
    assert cta.APPROVAL_SIGNER_UNTRUSTED in _codes(failures)


@requires_ssh_keygen
def test_tampered_document_breaks_signature():
    tampered = DOCUMENT_BYTES + b"\n<!-- tampered -->\n"
    ok, failures = _verify(
        approval=_approval(document_sha256=hashlib.sha256(tampered).hexdigest()),
        remote=_remote(document_bytes=tampered),
    )
    assert ok is False
    assert cta.APPROVAL_SIGNATURE_INVALID in _codes(failures)


@requires_ssh_keygen
def test_allowed_signers_from_candidate_checkout_is_rejected(tmp_path):
    """후보 checkout 이 심어 놓은 allowed_signers 로는 통과할 수 없다."""
    key = tmp_path / "candidate"
    subprocess.run(
        [_SSH_KEYGEN, "-t", "ed25519", "-N", "", "-C", "candidate", "-f", str(key)],
        capture_output=True,
        check=True,
    )
    public = (tmp_path / "candidate.pub").read_text(encoding="utf-8").strip()
    planted = tmp_path / "allowed_signers"
    planted.write_text(
        f'butler-approval-signer namespaces="butler-approval" {public}\n', encoding="utf-8"
    )
    document = tmp_path / "doc.md"
    document.write_bytes(DOCUMENT_BYTES)
    subprocess.run(
        [
            _SSH_KEYGEN, "-Y", "sign", "-f", str(key),
            "-n", SIGNATURE_NAMESPACE, str(document),
        ],
        capture_output=True,
        check=True,
    )
    forged_signature = (tmp_path / "doc.md.sig").read_bytes()

    ok, failures = _verify(
        remote=_remote(
            allowed_signers_bytes=planted.read_bytes(),
            signature_bytes=forged_signature,
        )
    )
    assert ok is False
    assert cta.APPROVAL_SIGNER_UNTRUSTED in _codes(failures)


def test_no_assert_in_verdict_path():
    """§E6-2 판정 경로에 assert 가 하나도 없어야 한다."""
    offenders: list[str] = []
    for source in sorted(AC25_SOURCE.glob("*.py")):
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"^\s*assert\b", line):
                offenders.append(f"{source.name}:{number}")
    assert offenders == []


@requires_ssh_keygen
def test_valid_signed_approval_passes():
    """정상 상태는 실제로 통과해야 한다. 막기만 하는 판정기는 통과로 보지 않는다."""
    ok, failures = _verify()
    assert failures == ()
    assert ok is True


# ── 회귀 보강 ─────────────────────────────────────────────────────────


def test_provenance_base_must_match_lock_base():
    ok, failures = _verify(approval=_approval(provenance_base_sha="0" * 40))
    assert ok is False
    assert cta.APPROVAL_COORDINATE_MISMATCH in _codes(failures)


def test_candidate_head_tree_mismatch_is_rejected():
    ok, failures = _verify(approval=_approval(candidate_head_tree="0" * 40))
    assert ok is False
    assert cta.APPROVAL_COORDINATE_MISMATCH in _codes(failures)


def test_approval_commit_not_fetchable_is_reported_separately():
    ok, failures = _verify(remote=_remote(approval_commit_fetchable=False))
    assert ok is False
    assert cta.APPROVAL_COMMIT_NOT_FETCHABLE in _codes(failures)


def test_approver_id_mismatch_with_real_account_is_rejected():
    ok, failures = _verify(remote=_remote(approver_id_for_login=999))
    assert ok is False
    assert cta.APPROVAL_SIGNER_UNTRUSTED in _codes(failures)


def test_expired_approval_is_rejected():
    ok, failures = _verify(now="2026-08-13T00:00:00Z")
    assert ok is False
    assert cta.APPROVAL_EXPIRED in _codes(failures)


def test_missing_approval_is_rejected():
    ok, failures = cta.verify_cross_track_approval(
        approval=None,
        anchor=ANCHOR,
        coordinates=COORDINATES,
        identity=IDENTITY,
        protected_changed_paths=APPROVED_PATHS,
        remote=_remote(),
        now=NOW,
    )
    assert ok is False
    assert cta.CROSS_TRACK_APPROVAL_NOT_FOUND in _codes(failures)


def test_pathset_mismatch_is_rejected():
    ok, failures = _verify(paths=APPROVED_PATHS | {"butler_sidecar.py"})
    assert ok is False
    assert cta.APPROVAL_PATHSET_MISMATCH in _codes(failures)


def test_every_failure_carries_evidence():
    """§7 증거가 하나도 없는 실패는 허용하지 않는다."""
    ok, failures = _verify(approval=_approval(candidate_head_sha="0" * 40))
    assert ok is False
    for failure in failures:
        assert failure.message
        assert failure.expected is not None or failure.observed is not None
