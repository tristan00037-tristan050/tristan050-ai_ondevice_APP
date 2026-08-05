"""§E7-1 단일 production orchestrator.

부품을 만들어 두고 워크플로가 부르지 않으면 검증은 존재하지 않는 것과 같다.
이 모듈이 유일한 production 진입점이며, 아래를 한 실행 경로로 묶는다.

    ① 원격 PR head/tree/base 재확인
    ② 승인 commit·문서·서명·allowed_signers 취득 (★고정 repo·commit·path 만)
    ③ 보호 ref 조상 여부 정확 확인 (compare API · 근사 금지)
    ④ 승인서 strict loader
    ⑤ 서명 · 경로 · 세 baseline · identity · 시각 검증
    ⑥ lock 검증
    ⑦ 보호 경로 완전일치
    ⑧ effective_expiry = min(lock.expires_at, approval.expires_at)

★로컬 경로 입력 인자를 두지 않는다. 승인 바이트는 로컬 파일에서 읽지 않는다.
★시험 픽스처를 읽지 않는다. 시험 디렉터리를 import 하지 않는다.
★하나라도 판정하지 못하면 통과시키지 않는다(fail-closed). assert 를 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from . import anchors, lock_verifier, protected_scope, remote_facts
from .approval_loader import ApprovalDocumentError, DocumentOrigin, load_approval_document
from .cross_track_approval import (
    ApprovalCoordinates,
    ApprovalFailure,
    IdentityDigests,
)

# ── 실패 코드 ──────────────────────────────────────────────────────────
ORCHESTRATOR_REMOTE_FACTS_INCOMPLETE = "ORCHESTRATOR_REMOTE_FACTS_INCOMPLETE"
ORCHESTRATOR_LOCK_FAILED = "ORCHESTRATOR_LOCK_FAILED"
ORCHESTRATOR_APPROVAL_DOCUMENT_INVALID = "ORCHESTRATOR_APPROVAL_DOCUMENT_INVALID"
ORCHESTRATOR_REMOTE_HEAD_MISMATCH = "ORCHESTRATOR_REMOTE_HEAD_MISMATCH"
ORCHESTRATOR_PROTECTED_SCOPE_FAILED = "ORCHESTRATOR_PROTECTED_SCOPE_FAILED"
ORCHESTRATOR_DIFF_NOT_MEASURED = "ORCHESTRATOR_DIFF_NOT_MEASURED"
EFFECTIVE_APPROVAL_EXPIRED = "EFFECTIVE_APPROVAL_EXPIRED"

# diff 를 신뢰할 수 없게 만드는 잠금 실패
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

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "failures": [
                    {
                        "code": f.code,
                        "message": f.message,
                        "expected": f.expected,
                        "observed": f.observed,
                    }
                    for f in self.failures
                ],
                "receipt": self.receipt,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


def trusted_repository_root() -> Path:
    """검증기 자신이 놓인 checkout 의 뿌리. 입력 인자가 아니다."""
    return Path(__file__).resolve().parents[3]


def designated_python_tests(lock) -> list[str]:
    """잠금 허용목록에서 유도한 후보 Python 검사 목록."""
    return sorted(
        path for path in lock.allowed_paths
        if path.startswith("tests/")
        and path.endswith(".py")
        and path.rsplit("/", 1)[-1].startswith("test_")
    )


def designated_js_tests(lock) -> list[str]:
    """잠금 허용목록에서 유도한 후보 JS/TS 검사 목록."""
    return sorted(
        path for path in lock.allowed_paths if path.endswith((".test.ts", ".test.tsx"))
    )


def _fail(code: str, message: str, expected: str, observed: str) -> ApprovalFailure:
    return ApprovalFailure(code, message, expected=expected, observed=observed)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_verification(
    *,
    transport: remote_facts.Transport,
    run_id: int,
    expected_head: str,
    expected_tree: str,
    verifier_commit: str,
    pr_number: int = anchors.CANDIDATE_PR_NUMBER,
    now: str | None = None,
    repository_root: Path | None = None,
) -> OrchestratorResult:
    """전 구간 검증. 성공 시에만 receipt 를 확정값으로 채운다."""
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

    # ── ⑥ 잠금: 좌표·identity 지문의 유일한 출처 ──────────────────────
    lock_path = root / anchors.CANDIDATE_LOCK_PATH
    try:
        lock = lock_verifier.load_candidate_lock(lock_path.read_bytes())
    except (OSError, lock_verifier.LockSchemaError) as exc:
        return OrchestratorResult(
            False,
            (_fail(ORCHESTRATOR_LOCK_FAILED, "후보 잠금을 로드하지 못했다",
                   anchors.CANDIDATE_LOCK_PATH, str(exc)),),
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

    receipt.update({
        "provenance_base_commit": lock.approved_base_commit,
        "provenance_base_tree": lock.approved_base_tree,
        "candidate_commit": lock.approved_head_commit,
        "candidate_tree": lock.approved_head_tree,
        "identity_manifest_sha256": lock.identity_manifest_sha256,
        "identity_artifact_zip_sha256": lock.identity_artifact_zip_sha256,
        "lock_expires_at": lock.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "changed_path_count": len(lock_verdict.changed_paths),
        # ★"지정된 후보 검사" 의 정의는 보호된 잠금에서 유도한다. 워크플로에
        #   손으로 적어 넣으면 부르는 쪽이 검사를 고를 수 있게 된다.
        "designated_python_tests": designated_python_tests(lock),
        "designated_js_tests": designated_js_tests(lock),
    })

    # ── ①②③ 원격 사실 ───────────────────────────────────────────────
    observation, remote_errors = remote_facts.collect_remote_facts(
        transport=transport,
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
            _fail(ORCHESTRATOR_REMOTE_FACTS_INCOMPLETE, f"[{error.code}] {error.message}",
                  error.expected or "", error.observed or "")
        )

    receipt.update({
        "protected_ref_head": observation.protected_ref_head,
        "observed_approval_repository": observation.observed_repository,
        "observed_protected_ref": observation.observed_protected_ref,
        "observed_document_path": observation.observed_document_path,
        "remote_candidate_head": observation.candidate_head_sha,
        "remote_candidate_tree": observation.candidate_head_tree,
        "integration_base_commit": observation.candidate_base_sha,
        "approval_commit_reachable": observation.facts.approval_commit_reachable,
        "approval_issued_at": observation.facts.approval_committer_utc,
        "run_started_at": observation.facts.run_started_at,
    })

    # ── 원격 head/tree 가 잠금과 완전히 같아야 한다(exact-head) ────────
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

    # ── ④ 승인서 strict load ─────────────────────────────────────────
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
            _fail(ORCHESTRATOR_APPROVAL_DOCUMENT_INVALID, f"[{exc.code}] {exc.message}",
                  anchors.APPROVAL_DOCUMENT_PATH, "엄격 로드 실패")
        )
        return OrchestratorResult(False, tuple(failures), receipt)

    receipt.update({
        "approval_document_sha256": anchors.APPROVAL_DOCUMENT_SHA256,
        "approver_login": approval.approver_login,
        "approver_id": approval.approver_id,
        "signing_key_fingerprint": approval.signing_key_fingerprint,
        "signature_namespace": approval.signature_namespace,
        "approval_expires_at": approval.expires_at,
    })

    # 승인자 실계정 ID 는 ★문서가 선언한 login★ 으로 다시 조회한다.
    # 워크플로 입력이 아니라 서명된 문서에서 온 값이라는 점이 요지다.
    resolved_id, id_errors = remote_facts.read_account_id(
        transport=transport, login=approval.approver_login
    )
    for error in id_errors:
        failures.append(
            _fail(ORCHESTRATOR_REMOTE_FACTS_INCOMPLETE, f"[{error.code}] {error.message}",
                  error.expected or "", error.observed or "")
        )
    facts = replace(observation.facts, approver_id_for_login=resolved_id)
    receipt["resolved_approver_id"] = resolved_id

    # ── ⑧ 실질 만료 = 더 이른 쪽 ─────────────────────────────────────
    effective = min(lock.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"), approval.expires_at)
    receipt["effective_expiry"] = effective
    if moment > effective:
        failures.append(
            _fail(EFFECTIVE_APPROVAL_EXPIRED, "실질 만료(둘 중 이른 쪽)를 지났다",
                  f"now <= {effective}", moment)
        )

    # ── ⑤⑦ 승인·보호 경로 판정 ──────────────────────────────────────
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
    receipt["protected_changed_paths"] = list(verdict.protected_changed_paths)
    if not verdict.ok:
        failures.extend(verdict.failures)
        failures.append(
            _fail(ORCHESTRATOR_PROTECTED_SCOPE_FAILED, "보호 범위 판정 실패",
                  "STATE_1_UNCHANGED 또는 STATE_2_APPROVED", verdict.state)
        )

    return OrchestratorResult(not failures, tuple(failures), receipt)


def build_parser() -> argparse.ArgumentParser:
    """★로컬 경로 입력 인자를 두지 않는다.

    승인 문서·서명·allowed_signers 의 위치는 anchors 에 고정돼 있고 오직 API 로만
    읽는다. 부르는 쪽이 파일을 가리킬 수 있으면 시험 픽스처를 먹일 수 있게 된다.
    """
    parser = argparse.ArgumentParser(
        description="AC-25 신뢰 검증 orchestrator (경로 입력 인자 없음)"
    )
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--verifier-commit", required=True)
    parser.add_argument("--pr-number", required=True, type=int)
    return parser


def _main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    if args.pr_number != anchors.CANDIDATE_PR_NUMBER:
        print(json.dumps({
            "ok": False,
            "failures": [{
                "code": "ORCHESTRATOR_PR_NUMBER_MISMATCH",
                "message": "고정된 후보 PR 번호가 아니다",
                "expected": str(anchors.CANDIDATE_PR_NUMBER),
                "observed": str(args.pr_number),
            }],
            "receipt": {},
        }, ensure_ascii=False, indent=2))
        return 1

    result = run_verification(
        transport=remote_facts.gh_transport,
        run_id=args.run_id,
        expected_head=args.expected_head,
        expected_tree=args.expected_tree,
        verifier_commit=args.verifier_commit,
        pr_number=args.pr_number,
    )
    print(result.to_json())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
