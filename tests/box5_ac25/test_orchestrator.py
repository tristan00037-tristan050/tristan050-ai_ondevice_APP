"""§E7-1 production orchestrator 시험.

이 시험군의 요지는 하나다 — ★워크플로가 부르는 단일 진입점이 다섯 부품을 모두
실제로 부르는가. 부품이 있어도 불리지 않으면 검증은 존재하지 않는다.

시각은 전부 주입한다(now= · lock_verifier._now monkeypatch). 실제 시계에 기대지
않으므로 하드코딩 만료일 시한폭탄이 되지 않는다.
"""
from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pytest
from ac25 import anchors, lock_verifier, orchestrator
from ac25 import remote_facts as rf

pytestmark = pytest.mark.no_sidecar_token

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SIG = (FIXTURES / "approval_document.md.sig").read_bytes()
SIGNERS = (FIXTURES / "allowed_signers").read_bytes()

PROTECTED_HEAD = "a" * 40
INTEGRATION_BASE = "b" * 40
ZIP_DIGEST = "5ea7f4b5355be5f4fd96b922c87f4530ddf6625abbef22848c091b2c629e2629"
MANIFEST_DIGEST = "b59e4aacd0d3f9bdd9874c838901c1ba0506478cfb15123536e729f83b4c2e4f"

NOW = "2026-08-05T06:00:00Z"
RUN_STARTED = "2026-08-05T05:00:00Z"
APPROVAL_COMMITTED = "2026-08-05T04:48:43Z"
APPROVAL_EXPIRES = "2030-06-01T00:00:00Z"
LOCK_EXPIRES = "2030-01-01T00:00:00Z"

PROTECTED_PATHS = (
    "butler-desktop/src/components/accounting_review/AccountingReviewPage.tsx",
    "butler-desktop/src/components/accounting_review/LearnedRuleSettings.tsx",
    "butler-desktop/src/lib/accounting_review/client.ts",
    "butler-desktop/src/lib/accounting_review/contracts.ts",
    "butler-desktop/src/lib/accounting_review/nativeAuthorizedRequest.test.ts",
    "butler-desktop/src/lib/accounting_review/nativeAuthorizedRequest.ts",
)
EXTRA_PATHS = (
    "tests/accounting/assignment/test_assignment_api.py",
    "butler-desktop/src/__tests__/AccountingReviewPage.test.tsx",
)


# ── 합성 승인 문서 ─────────────────────────────────────────────────────
def render_document(
    *,
    integration_base: str,
    provenance_base: str,
    provenance_base_tree: str,
    head: str,
    head_tree: str,
    expires: str = APPROVAL_EXPIRES,
    fingerprint: str = "SHA256:q87ozBPt1b218/lngOptVPRfFpgblANbUuvlUbu8HL4",
    paths: tuple[str, ...] = PROTECTED_PATHS,
) -> bytes:
    listed = "\n".join(paths)
    return f"""# 합성 교차 트랙 승인서

## 1. 두 기준선

integration_base_sha   {integration_base}
provenance_base_sha    {provenance_base}
provenance_base_tree   {provenance_base_tree}

## 2. 후보

candidate_head_sha           {head}
candidate_head_tree          {head_tree}
identity_artifact_zip_sha256 {ZIP_DIGEST}
identity_manifest_sha256     {MANIFEST_DIGEST}

## 3. 승인 경로

{listed}

## 4. 시각

expires_at  {expires}

## 5. 도장

approver_login  tristan00037-tristan050
approver_id     238947383
signing_key     {fingerprint}
namespace       butler-approval
signature_file  docs/decisions/approval.md.sig
allowed_signers docs/decisions/allowed_signers
""".encode()


# ── 합성 git 저장소 ────────────────────────────────────────────────────
def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    """base→head 두 커밋짜리 저장소. head 는 보호 경로 여섯을 바꾼다."""
    root = tmp_path / "candidate"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "verifier@example.invalid")
    _git(root, "config", "user.name", "verifier")

    for path in PROTECTED_PATHS + EXTRA_PATHS:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base_sha = _git(root, "rev-parse", "HEAD")
    base_tree = _git(root, "rev-parse", "HEAD^{tree}")

    for path in PROTECTED_PATHS + EXTRA_PATHS:
        (root / path).write_text("head\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "head")
    head_sha = _git(root, "rev-parse", "HEAD")
    head_tree = _git(root, "rev-parse", "HEAD^{tree}")

    # M-1 — 합성 저장소에도 해시 고정 manifest 를 둔다. 없으면 orchestrator 가
    # STAGE_B_DEPENDENCY_MANIFEST_NOT_FOUND 로 닫는다(그 자체가 배선 증거다).
    (root / "requirements-firstscreen-ci.lock").write_text(
        "pytest==9.1.1 \\\n    --hash=sha256:" + "1" * 64 + "\n"
        "pyyaml==6.0.3 \\\n    --hash=sha256:" + "2" * 64 + "\n",
        encoding="utf-8",
    )

    lock_path = root / anchors.CANDIDATE_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "schema_version": "butler.ac25.candidate_lock.v1",
                "repository": f"github.com/{anchors.CANDIDATE_REPOSITORY}",
                "pr_number": anchors.CANDIDATE_PR_NUMBER,
                "approved_base_commit": base_sha,
                "approved_base_tree": base_tree,
                "approved_head_commit": head_sha,
                "approved_head_tree": head_tree,
                "allowed_paths": sorted(PROTECTED_PATHS + EXTRA_PATHS),
                "identity_manifest_sha256": MANIFEST_DIGEST,
                "identity_artifact_zip_sha256": ZIP_DIGEST,
                "created_at": "2026-08-05T00:00:00Z",
                "expires_at": LOCK_EXPIRES,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "root": root,
        "base_sha": base_sha,
        "base_tree": base_tree,
        "head_sha": head_sha,
        "head_tree": head_tree,
    }


# ── 가짜 전송 ──────────────────────────────────────────────────────────
def _encoded(path: str) -> str:
    return quote(path, safe="/")


class FakeGitHub:
    def __init__(self, repo: dict, *, document: bytes) -> None:
        self.repo = repo
        self.document = document
        self.overrides: dict[str, rf.TransportResult] = {}
        self.requested: list[str] = []

    def _content(self, data: bytes, path: str) -> rf.TransportResult:
        return rf.TransportResult(
            status=200,
            payload={
                "path": path,
                "encoding": "base64",
                "content": base64.b64encode(data).decode("ascii"),
            },
        )

    def table(self) -> dict[str, rf.TransportResult]:
        ok = lambda payload: rf.TransportResult(status=200, payload=payload)  # noqa: E731
        approval = anchors.APPROVAL_REPOSITORY
        candidate = anchors.CANDIDATE_REPOSITORY
        commit = anchors.APPROVAL_COMMIT_SHA
        return {
            f"repos/{approval}": ok({"full_name": approval}),
            f"repos/{approval}/git/ref/heads/main": ok(
                {"ref": anchors.APPROVAL_PROTECTED_REF, "object": {"sha": PROTECTED_HEAD}}
            ),
            f"repos/{approval}/commits/{commit}": ok(
                {"sha": commit, "commit": {"committer": {"date": APPROVAL_COMMITTED}}}
            ),
            f"repos/{approval}/compare/{PROTECTED_HEAD}...{commit}": ok({"status": "behind"}),
            f"repos/{approval}/contents/{_encoded(anchors.APPROVAL_DOCUMENT_PATH)}"
            f"?ref={commit}": self._content(self.document, anchors.APPROVAL_DOCUMENT_PATH),
            f"repos/{approval}/contents/{_encoded(anchors.APPROVAL_SIGNATURE_PATH)}"
            f"?ref={commit}": self._content(SIG, anchors.APPROVAL_SIGNATURE_PATH),
            f"repos/{approval}/contents/{_encoded(anchors.APPROVAL_ALLOWED_SIGNERS_PATH)}"
            f"?ref={commit}": self._content(SIGNERS, anchors.APPROVAL_ALLOWED_SIGNERS_PATH),
            f"repos/{candidate}/actions/runs/77": ok({"run_started_at": RUN_STARTED}),
            f"repos/{candidate}/pulls/{anchors.CANDIDATE_PR_NUMBER}": ok(
                {
                    "head": {"sha": self.repo["head_sha"]},
                    "base": {"sha": INTEGRATION_BASE},
                }
            ),
            f"repos/{candidate}/git/commits/{self.repo['head_sha']}": ok(
                {"tree": {"sha": self.repo["head_tree"]}}
            ),
            "users/tristan00037-tristan050": ok({"id": 238947383}),
        }

    def __call__(self, path: str) -> rf.TransportResult:
        self.requested.append(path)
        if path in self.overrides:
            return self.overrides[path]
        return self.table().get(path, rf.TransportResult(status=404, message="not in table"))


@pytest.fixture
def document(repo) -> bytes:
    return render_document(
        integration_base=INTEGRATION_BASE,
        provenance_base=repo["base_sha"],
        provenance_base_tree=repo["base_tree"],
        head=repo["head_sha"],
        head_tree=repo["head_tree"],
    )


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setattr(
        lock_verifier, "_now", lambda: datetime(2026, 8, 5, 6, 0, tzinfo=timezone.utc)
    )


def _run(repo, transport, **kwargs):
    return orchestrator.run_verification(
        transport=transport,
        run_id=77,
        expected_head=kwargs.pop("expected_head", repo["head_sha"]),
        expected_tree=kwargs.pop("expected_tree", repo["head_tree"]),
        verifier_commit="9" * 40,
        now=kwargs.pop("now", NOW),
        repository_root=repo["root"],
        **kwargs,
    )


def _codes(result) -> set[str]:
    return {failure.code for failure in result.failures}


# ══ 배선: 다섯 부품이 실제로 불리는가 ═══════════════════════════════════
def test_orchestrator_actually_reads_every_remote_fact(repo, document, frozen_clock,
                                                       require_ssh_keygen):
    transport = FakeGitHub(repo, document=document)
    _run(repo, transport)
    approval = anchors.APPROVAL_REPOSITORY
    required = [
        f"repos/{approval}/git/ref/heads/main",
        f"repos/{approval}/commits/{anchors.APPROVAL_COMMIT_SHA}",
        f"repos/{approval}/compare/{PROTECTED_HEAD}...{anchors.APPROVAL_COMMIT_SHA}",
        "users/tristan00037-tristan050",
    ]
    for path in required:
        assert path in transport.requested, path
    assert any("/contents/" in path for path in transport.requested)
    assert any("/pulls/" in path for path in transport.requested)


def test_only_the_pinned_signature_and_digest_block_a_synthetic_case(
    repo, document, frozen_clock, require_ssh_keygen
):
    """합성 승인서는 서명과 고정 지문에서만 막혀야 한다.

    나머지 검사(좌표·경로·identity·시각·잠금·원격 head)가 모두 통과한다는 뜻이며,
    곧 orchestrator 가 그 검사들을 실제로 돌렸다는 뜻이다.
    """
    result = _run(repo, FakeGitHub(repo, document=document))
    assert result.ok is False
    assert _codes(result) == {
        "APPROVAL_DIGEST_MISMATCH",       # 고정 지문 != 합성 문서
        "APPROVAL_SIGNATURE_INVALID",     # 실물 서명은 합성 문서를 서명하지 않았다
        orchestrator.ORCHESTRATOR_PROTECTED_SCOPE_FAILED,
    }


# ══ 영수증: publish 가 요구하는 값이 모두 있는가 ═══════════════════════
def test_receipt_carries_every_field_publish_requires(repo, document, frozen_clock,
                                                      require_ssh_keygen):
    result = _run(repo, FakeGitHub(repo, document=document))
    receipt = result.receipt
    for key in (
        "candidate_commit", "candidate_tree", "provenance_base_commit",
        "integration_base_commit", "approval_commit", "approval_document_sha256",
        "identity_manifest_sha256", "identity_artifact_zip_sha256",
        "signing_key_fingerprint", "protected_ref_head", "effective_expiry",
        "protected_state", "dependency_manifest_sha256",
    ):
        assert receipt.get(key), key
    assert receipt["candidate_commit"] == repo["head_sha"]
    assert receipt["candidate_tree"] == repo["head_tree"]
    assert receipt["integration_base_commit"] == INTEGRATION_BASE
    assert receipt["protected_ref_head"] == PROTECTED_HEAD


def test_receipt_is_meta_only(repo, document, frozen_clock, require_ssh_keygen):
    """M-5 — receipt 에 raw path 목록이 들어가지 않는다."""
    receipt = _run(repo, FakeGitHub(repo, document=document)).receipt
    for key, value in receipt.items():
        assert not isinstance(value, (list, tuple)), f"{key} 가 목록이다"
        if isinstance(value, dict):
            assert False, f"{key} 가 중첩 객체다"
    assert receipt["protected_changed_path_count"] == 6
    assert receipt["changed_path_count"] == 8
    assert len(receipt["protected_changed_path_manifest_sha256"]) == 64
    assert len(receipt["changed_path_manifest_sha256"]) == 64
    assert receipt["offending_path_count"] == 0


def test_effective_expiry_is_the_earlier_of_lock_and_approval(repo, document, frozen_clock,
                                                              require_ssh_keygen):
    result = _run(repo, FakeGitHub(repo, document=document))
    assert result.receipt["lock_expires_at"] == LOCK_EXPIRES
    assert result.receipt["approval_expires_at"] == APPROVAL_EXPIRES
    assert result.receipt["effective_expiry"] == min(LOCK_EXPIRES, APPROVAL_EXPIRES)
    assert result.receipt["effective_expiry"] == LOCK_EXPIRES


def test_expiry_past_the_earlier_bound_is_rejected(repo, document, frozen_clock,
                                                   require_ssh_keygen):
    result = _run(repo, FakeGitHub(repo, document=document), now="2030-03-01T00:00:00Z")
    assert orchestrator.EFFECTIVE_APPROVAL_EXPIRED in _codes(result)


def test_coverage_contract_runs_and_records_its_basis(repo, document, frozen_clock,
                                                      require_ssh_keygen):
    """조건 1·2 — 덮음 계약이 실제로 돌고 근거가 영수증에 남는다."""
    from ac25.designated_checks import COVERAGE_BASIS

    result = _run(repo, FakeGitHub(repo, document=document))
    receipt = result.receipt
    assert receipt["coverage_basis"] == COVERAGE_BASIS
    assert receipt["coverage_uncovered_count"] == 0
    assert receipt["coverage_unreadable_count"] == 0
    # 이 합성 잠금의 tests 항목은 하나이며 직접 선택된다
    assert receipt["coverage_entry_count"] == 1
    assert receipt["coverage_covered_count"] == 1


def test_coverage_gap_fails_the_whole_run(repo, document, frozen_clock,
                                          require_ssh_keygen, monkeypatch):
    """조건 3 — 참조가 끊기면 orchestrator 전체가 실패한다."""
    from ac25 import designated_checks

    real = designated_checks.verify_designated_coverage

    def gapped(*, lock, read_blob):
        report = real(lock=lock, read_blob=read_blob)
        return replace(report, uncovered=("tests/fixtures/some_helper.json",))

    monkeypatch.setattr(orchestrator.designated_checks, "verify_designated_coverage", gapped)
    result = _run(repo, FakeGitHub(repo, document=document))
    assert result.ok is False
    assert designated_checks.DESIGNATED_CHECK_COVERAGE_GAP in _codes(result)


def test_designated_checks_are_derived_from_the_lock(repo, document, frozen_clock,
                                                     require_ssh_keygen):
    receipt = _run(repo, FakeGitHub(repo, document=document)).receipt
    assert receipt["designated_python_test_count"] == 1
    assert receipt["designated_js_test_count"] == 2
    assert len(receipt["designated_test_manifest_sha256"]) == 64


# ══ fail-closed 갈래 ═══════════════════════════════════════════════════
def test_missing_lock_is_fail_closed(tmp_path, frozen_clock):
    empty = {"root": tmp_path, "head_sha": "6" * 40, "head_tree": "3" * 40}
    result = orchestrator.run_verification(
        transport=lambda path: rf.TransportResult(status=404),
        run_id=77, expected_head="6" * 40, expected_tree="3" * 40,
        verifier_commit="9" * 40, now=NOW, repository_root=tmp_path,
    )
    assert result.ok is False
    assert orchestrator.ORCHESTRATOR_LOCK_FAILED in _codes(result)


def test_remote_head_disagreeing_with_lock_is_rejected(repo, document, frozen_clock,
                                                       require_ssh_keygen):
    transport = FakeGitHub(repo, document=document)
    transport.overrides[
        f"repos/{anchors.CANDIDATE_REPOSITORY}/pulls/{anchors.CANDIDATE_PR_NUMBER}"
    ] = rf.TransportResult(
        status=200, payload={"head": {"sha": "e" * 40}, "base": {"sha": INTEGRATION_BASE}}
    )
    result = _run(repo, transport)
    assert orchestrator.ORCHESTRATOR_REMOTE_HEAD_MISMATCH in _codes(result)


def test_unreachable_approval_commit_is_rejected(repo, document, frozen_clock,
                                                 require_ssh_keygen):
    transport = FakeGitHub(repo, document=document)
    transport.overrides[
        f"repos/{anchors.APPROVAL_REPOSITORY}/compare/"
        f"{PROTECTED_HEAD}...{anchors.APPROVAL_COMMIT_SHA}"
    ] = rf.TransportResult(status=200, payload={"status": "diverged"})
    result = _run(repo, transport)
    assert "APPROVAL_COMMIT_NOT_REACHABLE" in _codes(result)


def test_missing_document_bytes_is_fail_closed(repo, document, frozen_clock):
    transport = FakeGitHub(repo, document=document)
    transport.overrides[
        f"repos/{anchors.APPROVAL_REPOSITORY}/contents/"
        f"{_encoded(anchors.APPROVAL_DOCUMENT_PATH)}?ref={anchors.APPROVAL_COMMIT_SHA}"
    ] = rf.TransportResult(status=404)
    result = _run(repo, transport)
    assert result.ok is False
    assert orchestrator.ORCHESTRATOR_APPROVAL_DOCUMENT_INVALID in _codes(result)


def test_two_baselines_in_one_field_is_rejected(repo, frozen_clock, require_ssh_keygen):
    collapsed = render_document(
        integration_base=repo["base_sha"],   # 통합 base 칸에 경로 base 를 넣음
        provenance_base=repo["base_sha"],
        provenance_base_tree=repo["base_tree"],
        head=repo["head_sha"],
        head_tree=repo["head_tree"],
    )
    result = _run(repo, FakeGitHub(repo, document=collapsed))
    assert "BASELINE_ROLE_MISMATCH" in _codes(result)


def test_extra_approved_path_breaks_exact_match(repo, frozen_clock, require_ssh_keygen):
    widened = render_document(
        integration_base=INTEGRATION_BASE,
        provenance_base=repo["base_sha"],
        provenance_base_tree=repo["base_tree"],
        head=repo["head_sha"],
        head_tree=repo["head_tree"],
        paths=PROTECTED_PATHS + ("butler-desktop/src/lib/accounting_review/extra.ts",),
    )
    result = _run(repo, FakeGitHub(repo, document=widened))
    assert "APPROVAL_PATHSET_MISMATCH" in _codes(result)


def test_untrusted_fingerprint_in_document_is_rejected(repo, frozen_clock, require_ssh_keygen):
    forged = render_document(
        integration_base=INTEGRATION_BASE,
        provenance_base=repo["base_sha"],
        provenance_base_tree=repo["base_tree"],
        head=repo["head_sha"],
        head_tree=repo["head_tree"],
        fingerprint="SHA256:" + "A" * 43,
    )
    result = _run(repo, FakeGitHub(repo, document=forged))
    assert "APPROVAL_SIGNER_UNTRUSTED" in _codes(result)


def test_cli_emits_two_meta_only_lines_on_failure(capsys, monkeypatch, tmp_path):
    """M-5 — 실패해도 공개 출력은 정확히 두 줄이다."""
    monkeypatch.setattr(orchestrator, "trusted_repository_root", lambda: tmp_path)
    assert orchestrator._main([]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        "VERDICT=0",
        f"ERROR_CODE={orchestrator.ORCHESTRATOR_LOCK_FAILED}",
    ]


def test_every_failure_carries_evidence(repo, document, frozen_clock, require_ssh_keygen):
    result = _run(repo, FakeGitHub(repo, document=document))
    assert result.failures
    for failure in result.failures:
        assert failure.expected is not None or failure.observed is not None
        assert failure.message
