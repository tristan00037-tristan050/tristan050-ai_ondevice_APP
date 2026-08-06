"""§11 단일 production orchestrator.

부품을 만들어 두고 워크플로가 부르지 않으면 검증은 존재하지 않는 것과 같다.
이 모듈이 유일한 production 진입점이며, 아래를 한 실행 경로로 묶는다.

    dispatch input strict 검증           (M-4)
    workflow identity·environment 검증   (M-2)
    PR #903 remote head·tree·base 확인
    승인 commit·문서·서명·signer 취득
    승인 보호 ref 조상 확인
    승인 strict load
    승인 signature·coordinates·paths·time 검증
    candidate lock 검증
    protected scope 완전일치
    dependency manifest resolve          (M-1)
    지정 Python·JS 검사 목록 생성
    effective expiry 계산
    meta-only receipt 원자적 기록        (M-5)

★로컬 경로 입력 인자를 두지 않는다. 승인 바이트는 로컬 파일에서 읽지 않는다.
★시험 픽스처를 읽지 않는다. 시험 디렉터리를 import 하지 않는다.
★공개 출력은 VERDICT 와 ERROR_CODE 두 줄뿐이다(§9).
★하나라도 판정하지 못하면 통과시키지 않는다(fail-closed). assert 를 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from . import (
    anchors,
    dependency_manifest,
    designated_checks,
    lock_verifier,
    protected_scope,
    output_containment,
    remote_facts,
    workflow_identity,
    workflow_inputs,
)
from .approval_loader import ApprovalDocumentError, DocumentOrigin, load_approval_document
from .cross_track_approval import ApprovalCoordinates, ApprovalFailure, IdentityDigests

# ── 실패 코드 ──────────────────────────────────────────────────────────
ORCHESTRATOR_REMOTE_FACTS_INCOMPLETE = "ORCHESTRATOR_REMOTE_FACTS_INCOMPLETE"
ORCHESTRATOR_LOCK_FAILED = "ORCHESTRATOR_LOCK_FAILED"
ORCHESTRATOR_APPROVAL_DOCUMENT_INVALID = "ORCHESTRATOR_APPROVAL_DOCUMENT_INVALID"
ORCHESTRATOR_REMOTE_HEAD_MISMATCH = "ORCHESTRATOR_REMOTE_HEAD_MISMATCH"
ORCHESTRATOR_PROTECTED_SCOPE_FAILED = "ORCHESTRATOR_PROTECTED_SCOPE_FAILED"
ORCHESTRATOR_DIFF_NOT_MEASURED = "ORCHESTRATOR_DIFF_NOT_MEASURED"
ORCHESTRATOR_RECEIPT_WRITE_FAILED = "ORCHESTRATOR_RECEIPT_WRITE_FAILED"
EFFECTIVE_APPROVAL_EXPIRED = "EFFECTIVE_APPROVAL_EXPIRED"

RECEIPT_FILENAME = "ac25-receipt.json"

_DIFF_BLOCKING_CODES = frozenset({
    lock_verifier.CHANGED_PATHS_UNAVAILABLE,
    lock_verifier.GIT_ANCESTRY_INVALID,
    lock_verifier.GIT_OBJECT_NOT_FOUND,
})


@dataclass(frozen=True)
class OrchestratorResult:
    ok: bool
    failures: tuple[ApprovalFailure, ...] = ()
    receipt: dict = field(default_factory=dict)

    @property
    def error_code(self) -> str:
        """★공개 출력에 쓰는 짧은 ASCII 코드 하나."""
        return "OK" if self.ok else (self.failures[0].code if self.failures else "UNKNOWN")


def path_manifest_sha256(paths) -> str:
    """경로 목록의 지문. ★목록 자체는 공개하지 않고 이 값만 싣는다(§9)."""
    joined = "\n".join(sorted(paths))
    return hashlib.sha256((joined + "\n").encode("utf-8")).hexdigest()


def trusted_repository_root() -> Path:
    """검증기 자신이 놓인 checkout 의 뿌리. 입력 인자가 아니다."""
    return Path(__file__).resolve().parents[3]


def git_blob_reader(root: Path, commit: str) -> designated_checks.BlobReader:
    """후보 head 의 원문 바이트를 읽는다.

    ★후보 코드를 실행하지 않는다. checkout 도 하지 않는다. blob 을 꺼낼 뿐이다.
    """

    def read(path: str) -> bytes | None:
        try:
            code, out, _err = output_containment.run_and_read(
                ["git", "-C", str(root), "show", f"{commit}:{path}"], cwd=root
            )
        except output_containment.ContainmentError:
            return None
        return out if code == 0 else None

    return read


def production_router() -> remote_facts.TransportRouter:
    """★승인 저장소와 후보 저장소를 ★다른 credential★ 로 읽는다(C5).

    한쪽 열쇠로 다른 쪽 문을 열 수 있으면 최소권한이 아니다.
    """
    return remote_facts.TransportRouter(
        approval=remote_facts.gh_transport_for(remote_facts.APPROVAL_TOKEN_ENV),
        candidate=remote_facts.gh_transport_for(remote_facts.CANDIDATE_TOKEN_ENV),
        run=remote_facts.gh_transport_for(remote_facts.CANDIDATE_TOKEN_ENV),
    )


def _fail(code: str, message: str, expected: str, observed: str) -> ApprovalFailure:
    return ApprovalFailure(code, message, expected=expected, observed=observed)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_verification(
    *,
    router: remote_facts.TransportRouter,
    run_id: int,
    expected_head: str,
    expected_tree: str,
    verifier_commit: str,
    pr_number: int = anchors.CANDIDATE_PR_NUMBER,
    now: str | None = None,
    repository_root: Path | None = None,
) -> OrchestratorResult:
    """전 구간 검증. receipt 는 meta-only 로만 채운다(§9)."""
    moment = now or _utc_now()
    root = repository_root or trusted_repository_root()
    anchor = anchors.production_trust_anchor()
    failures: list[ApprovalFailure] = []
    receipt: dict = {
        "verifier_commit": verifier_commit,
        "checked_at": moment,
        "approval_repository": anchors.APPROVAL_REPOSITORY,
        "approval_commit": anchors.APPROVAL_COMMIT_SHA,
        "protected_ref": anchors.APPROVAL_PROTECTED_REF,
        "candidate_repository": anchors.CANDIDATE_REPOSITORY,
        "pr_number": pr_number,
    }

    # ── 잠금: 좌표·identity 지문의 유일한 출처 ────────────────────────
    lock_path = root / anchors.CANDIDATE_LOCK_PATH
    try:
        lock = lock_verifier.load_candidate_lock(lock_path.read_bytes())
    except (OSError, lock_verifier.LockSchemaError) as exc:
        return OrchestratorResult(
            False,
            (_fail(ORCHESTRATOR_LOCK_FAILED, "후보 잠금을 로드하지 못했다",
                   anchors.CANDIDATE_LOCK_PATH, type(exc).__name__),),
            receipt,
        )

    lock_verdict = lock_verifier.verify_integration_lock(
        repository_path=str(root),
        lock_path=str(lock_path),
        expected_head=expected_head,
        expected_tree=expected_tree,
        execution_commit=lock.approved_head_commit,
    )
    for evidence in lock_verdict.failures:
        failures.append(
            _fail(ORCHESTRATOR_LOCK_FAILED, f"[{evidence.code}] {evidence.message}",
                  evidence.expected or "", evidence.observed or "")
        )
    diff_measured = not any(f.code in _DIFF_BLOCKING_CODES for f in lock_verdict.failures)
    if not diff_measured:
        failures.append(
            _fail(ORCHESTRATOR_DIFF_NOT_MEASURED, "base..head 변경 경로를 측정하지 못했다",
                  f"{lock.approved_base_commit}..{lock.approved_head_commit}", "측정 실패")
        )

    # ★경로 목록이 아니라 개수와 지문만 싣는다(§9)
    receipt.update({
        "provenance_base_commit": lock.approved_base_commit,
        "provenance_base_tree": lock.approved_base_tree,
        "candidate_commit": lock.approved_head_commit,
        "candidate_tree": lock.approved_head_tree,
        "identity_manifest_sha256": lock.identity_manifest_sha256,
        "identity_artifact_zip_sha256": lock.identity_artifact_zip_sha256,
        "lock_expires_at": lock.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "changed_path_count": len(lock_verdict.changed_paths),
        "changed_path_manifest_sha256": path_manifest_sha256(lock_verdict.changed_paths),
        "offending_path_count": len(lock_verdict.offending_paths),
        "offending_path_manifest_sha256": path_manifest_sha256(lock_verdict.offending_paths),
    })

    # ── M-1 dependency manifest ───────────────────────────────────────
    try:
        manifest = dependency_manifest.resolve_manifest(
            repo_root=root, test_root=root / "tests" / "box5_ac25"
        )
        receipt.update({
            "dependency_manifest_path": manifest.relative_path,
            "dependency_manifest_sha256": manifest.sha256,
            "dependency_hash_pinned": manifest.hash_pinned,
            "dependency_required_count": len(manifest.required_distributions),
        })
    except dependency_manifest.DependencyManifestError as exc:
        failures.append(
            _fail(exc.code, "dependency manifest 해석 실패",
                  ",".join(dependency_manifest.MANIFEST_CANDIDATES), "실패")
        )

    # ── 지정 검사 목록과 덮음 계약 ────────────────────────────────────
    python_tests = designated_checks.designated_python_tests(lock)
    js_tests = designated_checks.designated_js_tests(lock)
    coverage = designated_checks.verify_designated_coverage(
        lock=lock, read_blob=git_blob_reader(root, lock.approved_head_commit)
    )
    receipt.update({
        "designated_python_test_count": len(python_tests),
        "designated_js_test_count": len(js_tests),
        "designated_test_manifest_sha256": path_manifest_sha256(python_tests + js_tests),
        "coverage_basis": coverage.basis,
        "coverage_entry_count": len(coverage.lock_test_entries),
        "coverage_covered_count": (
            len(coverage.directly_selected) + len(coverage.indirectly_covered)
        ),
        "coverage_uncovered_count": len(coverage.uncovered),
        "coverage_unreadable_count": len(coverage.unreadable),
    })
    if not coverage.ok:
        failures.append(
            _fail(designated_checks.DESIGNATED_CHECK_COVERAGE_GAP,
                  "잠금 tests 항목이 지정 검사에 덮이지 않는다",
                  f"{len(coverage.lock_test_entries)}개 전부 덮임",
                  f"uncovered={len(coverage.uncovered)} unreadable={len(coverage.unreadable)}")
        )

    # ── 원격 사실 ─────────────────────────────────────────────────────
    observation, remote_errors = remote_facts.collect_remote_facts(
        router=router,
        approval_repository=anchors.APPROVAL_REPOSITORY,
        approval_protected_ref=anchors.APPROVAL_PROTECTED_REF,
        approval_commit_sha=anchors.APPROVAL_COMMIT_SHA,
        document_path=anchors.APPROVAL_DOCUMENT_PATH,
        signature_path=anchors.APPROVAL_SIGNATURE_PATH,
        allowed_signers_path=anchors.APPROVAL_ALLOWED_SIGNERS_PATH,
        candidate_repository=anchors.CANDIDATE_REPOSITORY,
        pr_number=pr_number,
        run_repository=anchors.CANDIDATE_REPOSITORY,
        run_id=run_id,
    )
    for error in remote_errors:
        failures.append(
            _fail(ORCHESTRATOR_REMOTE_FACTS_INCOMPLETE, error.message, "", error.code)
        )

    receipt.update({
        "protected_ref_head": observation.protected_ref_head,
        "remote_candidate_head": observation.candidate_head_sha,
        "remote_candidate_tree": observation.candidate_head_tree,
        "integration_base_commit": observation.candidate_base_sha,
        "approval_commit_reachable": observation.facts.approval_commit_reachable,
        "approval_issued_at": observation.facts.approval_committer_utc,
        "run_started_at": observation.facts.run_started_at,
    })

    if observation.candidate_head_sha != lock.approved_head_commit:
        failures.append(
            _fail(ORCHESTRATOR_REMOTE_HEAD_MISMATCH, "원격 PR head 가 잠금 head 와 다르다",
                  lock.approved_head_commit, observation.candidate_head_sha or "읽기 실패")
        )
    if observation.candidate_head_tree != lock.approved_head_tree:
        failures.append(
            _fail(ORCHESTRATOR_REMOTE_HEAD_MISMATCH, "원격 PR head tree 가 잠금 tree 와 다르다",
                  lock.approved_head_tree, observation.candidate_head_tree or "읽기 실패")
        )

    # ── 승인서 strict load ────────────────────────────────────────────
    document_bytes = observation.facts.document_bytes
    if document_bytes is None:
        failures.append(
            _fail(ORCHESTRATOR_APPROVAL_DOCUMENT_INVALID, "승인 문서 바이트를 얻지 못했다",
                  anchors.APPROVAL_DOCUMENT_PATH, "없음")
        )
        return OrchestratorResult(False, tuple(failures), receipt)

    origin = DocumentOrigin(
        repository=observation.observed_repository,
        protected_ref=observation.observed_protected_ref,
        document_path=observation.observed_document_path,
        approval_commit_sha=anchors.APPROVAL_COMMIT_SHA,
    )
    try:
        approval = load_approval_document(
            document_bytes,
            origin=origin,
            pinned_document_sha256=anchors.APPROVAL_DOCUMENT_SHA256,
        )
    except ApprovalDocumentError as exc:
        failures.append(
            _fail(ORCHESTRATOR_APPROVAL_DOCUMENT_INVALID, "승인 문서 엄격 로드 실패",
                  anchors.APPROVAL_DOCUMENT_PATH, exc.code)
        )
        return OrchestratorResult(False, tuple(failures), receipt)

    receipt.update({
        "approval_document_sha256": anchors.APPROVAL_DOCUMENT_SHA256,
        "signing_key_fingerprint": approval.signing_key_fingerprint,
        "approval_expires_at": approval.expires_at,
    })

    resolved_id, id_errors = remote_facts.read_account_id(
        transport=router.approval, login=approval.approver_login
    )
    for error in id_errors:
        failures.append(
            _fail(ORCHESTRATOR_REMOTE_FACTS_INCOMPLETE, error.message, "", error.code)
        )
    facts = replace(observation.facts, approver_id_for_login=resolved_id)

    # ── 실질 만료 = 더 이른 쪽 ────────────────────────────────────────
    effective = min(lock.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"), approval.expires_at)
    receipt["effective_expiry"] = effective
    if moment > effective:
        failures.append(
            _fail(EFFECTIVE_APPROVAL_EXPIRED, "실질 만료(둘 중 이른 쪽)를 지났다",
                  f"now <= {effective}", moment)
        )

    # ── 승인·보호 경로 판정 ───────────────────────────────────────────
    coordinates = ApprovalCoordinates(
        candidate_head_sha=lock.approved_head_commit,
        candidate_head_tree=lock.approved_head_tree,
        provenance_base_sha=lock.approved_base_commit,
        provenance_base_tree=lock.approved_base_tree,
        integration_comparison_base=observation.candidate_base_sha,
    )
    identity = IdentityDigests(
        identity_artifact_zip_sha256=lock.identity_artifact_zip_sha256,
        identity_manifest_sha256=lock.identity_manifest_sha256,
    )
    verdict = protected_scope.evaluate_protected_scope(
        changed_paths=frozenset(lock_verdict.changed_paths),
        verified_unchanged=diff_measured,
        approval=approval,
        anchor=anchor,
        coordinates=coordinates,
        identity=identity,
        remote=facts,
        now=moment,
    )
    receipt["protected_state"] = verdict.state
    # ★경로 목록이 아니라 개수와 지문만(§9)
    receipt["protected_changed_path_count"] = len(verdict.protected_changed_paths)
    receipt["protected_changed_path_manifest_sha256"] = path_manifest_sha256(
        verdict.protected_changed_paths
    )
    if not verdict.ok:
        failures.extend(verdict.failures)
        failures.append(
            _fail(ORCHESTRATOR_PROTECTED_SCOPE_FAILED, "보호 범위 판정 실패",
                  "STATE_1_UNCHANGED 또는 STATE_2_APPROVED", verdict.state)
        )

    result = OrchestratorResult(not failures, tuple(failures), receipt)
    receipt["verdict"] = 1 if result.ok else 0
    receipt["error_code"] = result.error_code
    return result


# ══ M-4 · M-2 진입 검증 ════════════════════════════════════════════════
def verify_dispatch_and_identity(
    *,
    environ,
    router: remote_facts.TransportRouter,
    locked_head: str,
    locked_tree: str,
) -> workflow_inputs.DispatchInputs:
    """★셸 본문이 아니라 env 로 받은 값을 strict 검증한다(M-4).

    이어서 workflow 신원과 environment 정책을 원격 사실로 강제한다(M-2).
    """
    inputs = workflow_inputs.validate_dispatch_inputs(
        pr_number=environ.get("AC25_PR_NUMBER"),
        expected_head=environ.get("AC25_EXPECTED_HEAD"),
        expected_tree=environ.get("AC25_EXPECTED_TREE"),
        run_id=environ.get("GITHUB_RUN_ID"),
        repository=environ.get("GITHUB_REPOSITORY"),
        ref=environ.get("GITHUB_REF"),
        event_name=environ.get("GITHUB_EVENT_NAME"),
        locked_head=locked_head,
        locked_tree=locked_tree,
    )

    identity = workflow_identity.WorkflowIdentity(
        event_name=str(environ.get("GITHUB_EVENT_NAME") or ""),
        repository=str(environ.get("GITHUB_REPOSITORY") or ""),
        ref=str(environ.get("GITHUB_REF") or ""),
        ref_protected=str(environ.get("GITHUB_REF_PROTECTED") or "").lower() == "true",
        sha=str(environ.get("GITHUB_SHA") or ""),
        run_id=inputs.run_id,
        run_attempt=str(environ.get("GITHUB_RUN_ATTEMPT") or ""),
        actor_id=str(environ.get("GITHUB_ACTOR_ID") or ""),
    )
    facts, errors = remote_facts.read_protected_facts(
        router=router,
        repository=workflow_identity.EXPECTED_REPOSITORY,
        protected_ref=workflow_identity.EXPECTED_REF,
        environment_name=workflow_identity.EXPECTED_ENVIRONMENT,
    )
    if errors:
        raise workflow_identity.WorkflowIdentityError(
            workflow_identity.TRUSTED_WORKFLOW_REMOTE_FACT_UNAVAILABLE
        )
    workflow_identity.verify_workflow_identity(
        identity=identity, facts=facts, verifier_commit=identity.sha
    )
    return inputs


def write_receipt(receipt: dict, *, directory: Path) -> tuple[Path, str]:
    """§9·C6 — receipt 를 RUNNER_TEMP 아래에 mode 0600 으로 ★원자 기록★ 한다.

    ★원문은 job output·env 로 나가지 않는다. 나가는 것은 이 digest 뿐이다.
    """
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / RECEIPT_FILENAME
    payload = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    handle, temporary = tempfile.mkstemp(dir=str(directory), prefix=".ac25-receipt-")
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return target, digest


# ★C6 — job output 은 이 여섯만 허용한다. 원문·경로·응답은 0건이다.
JOB_OUTPUT_ALLOWLIST = (
    "verdict",
    "error_code",
    "receipt_sha256",
    "candidate_commit",
    "candidate_tree",
    "changed_path_count",
)

_SINGLE_LINE = __import__("re").compile(r"\A[A-Za-z0-9_.:-]{1,128}\Z")


def job_outputs(result: "OrchestratorResult", *, receipt_sha256: str) -> dict:
    """허용 목록 값만, 한 줄 형식으로 검증해 내보낸다."""
    receipt = result.receipt
    values = {
        "verdict": "1" if result.ok else "0",
        "error_code": result.error_code,
        "receipt_sha256": receipt_sha256,
        "candidate_commit": str(receipt.get("candidate_commit", "")),
        "candidate_tree": str(receipt.get("candidate_tree", "")),
        "changed_path_count": str(receipt.get("changed_path_count", "")),
    }
    for key, value in values.items():
        if key not in JOB_OUTPUT_ALLOWLIST or not _SINGLE_LINE.match(value):
            raise ValueError("JOB_OUTPUT_INVALID")
    return values


def _emit(verdict: int, error_code: str) -> None:
    """★공개 출력은 정확히 두 줄. traceback·경로·원문을 내지 않는다(§9)."""
    print(f"VERDICT={verdict}")
    print(f"ERROR_CODE={error_code}")


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="AC-25 신뢰 검증 orchestrator (경로·값 입력 인자 없음)"
    )
    parser.add_argument("--mode", default="verify", choices=("verify",))
    parser.parse_args(argv)

    environ = os.environ
    root = trusted_repository_root()

    try:
        lock = lock_verifier.load_candidate_lock(
            (root / anchors.CANDIDATE_LOCK_PATH).read_bytes()
        )
    except (OSError, lock_verifier.LockSchemaError):
        _emit(0, ORCHESTRATOR_LOCK_FAILED)
        return 1

    try:
        inputs = verify_dispatch_and_identity(
            environ=environ,
            router=production_router(),
            locked_head=lock.approved_head_commit,
            locked_tree=lock.approved_head_tree,
        )
    except workflow_inputs.WorkflowInputError as exc:
        _emit(0, exc.code)
        return 1
    except workflow_identity.WorkflowIdentityError as exc:
        _emit(0, exc.code)
        return 1

    result = run_verification(
        router=production_router(),
        run_id=int(inputs.run_id),
        expected_head=inputs.expected_head,
        expected_tree=inputs.expected_tree,
        verifier_commit=str(environ.get("GITHUB_SHA") or ""),
        pr_number=int(inputs.pr_number),
        repository_root=root,
    )

    runner_temp = environ.get("RUNNER_TEMP")
    try:
        _path, receipt_sha256 = write_receipt(
            result.receipt,
            directory=Path(runner_temp) if runner_temp else root / ".ac25",
        )
    except OSError:
        _emit(0, ORCHESTRATOR_RECEIPT_WRITE_FAILED)
        return 1

    # ★C6 — 허용 목록 값만 job output 으로 내보낸다. receipt 원문은 나가지 않는다.
    output_file = environ.get("GITHUB_OUTPUT")
    if output_file:
        try:
            with open(output_file, "a", encoding="utf-8") as stream:
                for key, value in job_outputs(result, receipt_sha256=receipt_sha256).items():
                    stream.write(f"{key}={value}\n")
        except (OSError, ValueError):
            _emit(0, ORCHESTRATOR_RECEIPT_WRITE_FAILED)
            return 1

    _emit(1 if result.ok else 0, result.error_code)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
