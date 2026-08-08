"""§6 M-2 — 보호된 main workflow 신원과 외부 environment 강제.

감사 PRIMARY_BLOCK: TRUSTED_WORKFLOW_REF_NOT_ENFORCED.
"이 워크플로는 main 에서만 돈다" 를 전제로만 두었고 검사하지 않았다.

★자기 자신을 검사하는 코드는, 그 코드를 고칠 수 있는 자에게는 검사가 아니다.
  그래서 이 모듈(내부 검사)과 environment 의 branch 정책(외부 강제)이 함께 있어야
  한다. 이 모듈만으로는 다른 branch 의 workflow 가 검사 자체를 지울 수 있다.

★workflow context 와 remote facts 를 같은 값에서 복제하지 않는다.
  context 는 러너가 준 값이고 remote facts 는 GitHub API 응답이다. 둘을 한 곳에서
  베끼면 대조가 자기증명이 된다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED_EVENTS = frozenset({"workflow_dispatch"})
EXPECTED_REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
EXPECTED_REF = "refs/heads/main"
EXPECTED_ENVIRONMENT = "ac25-trusted-main"

# ── 오류 코드 (§6) ─────────────────────────────────────────────────────
TRUSTED_WORKFLOW_EVENT_NOT_ALLOWED = "TRUSTED_WORKFLOW_EVENT_NOT_ALLOWED"
TRUSTED_WORKFLOW_REPOSITORY_MISMATCH = "TRUSTED_WORKFLOW_REPOSITORY_MISMATCH"
TRUSTED_WORKFLOW_REF_NOT_MAIN = "TRUSTED_WORKFLOW_REF_NOT_MAIN"
TRUSTED_WORKFLOW_REF_NOT_PROTECTED = "TRUSTED_WORKFLOW_REF_NOT_PROTECTED"
TRUSTED_WORKFLOW_REMOTE_MAIN_NOT_PROTECTED = "TRUSTED_WORKFLOW_REMOTE_MAIN_NOT_PROTECTED"
TRUSTED_WORKFLOW_SHA_NOT_PROTECTED_HEAD = "TRUSTED_WORKFLOW_SHA_NOT_PROTECTED_HEAD"
TRUSTED_WORKFLOW_VERIFIER_MISMATCH = "TRUSTED_WORKFLOW_VERIFIER_MISMATCH"
TRUSTED_ENVIRONMENT_NOT_FOUND = "TRUSTED_ENVIRONMENT_NOT_FOUND"
TRUSTED_ENVIRONMENT_POLICY_MISMATCH = "TRUSTED_ENVIRONMENT_POLICY_MISMATCH"
TRUSTED_WORKFLOW_REMOTE_FACT_UNAVAILABLE = "TRUSTED_WORKFLOW_REMOTE_FACT_UNAVAILABLE"

_OID_RE = re.compile(r"\A[0-9a-f]{40}\Z")


class WorkflowIdentityError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class WorkflowIdentity:
    """러너가 준 workflow context."""
    event_name: str
    repository: str
    ref: str
    ref_protected: bool
    sha: str
    run_id: str
    run_attempt: str
    actor_id: str


@dataclass(frozen=True)
class ProtectedFacts:
    """GitHub API 응답에서 얻은 값. context 를 베낀 것이 아니다."""
    repository: str
    main_ref: str
    main_head: str
    main_protected: bool
    environment_name: str
    environment_main_only: bool


def verify_workflow_identity(
    *,
    identity: WorkflowIdentity,
    facts: ProtectedFacts,
    verifier_commit: str,
) -> None:
    """불변식이 하나라도 깨지면 예외로 닫는다. 통과하면 아무것도 돌려주지 않는다."""
    if identity.event_name not in ALLOWED_EVENTS:
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_EVENT_NOT_ALLOWED)
    if identity.repository != EXPECTED_REPOSITORY:
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_REPOSITORY_MISMATCH)
    if identity.ref != EXPECTED_REF:
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_REF_NOT_MAIN)
    if identity.ref_protected is not True:
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_REF_NOT_PROTECTED)

    # ── 원격 사실 ─────────────────────────────────────────────────────
    if (
        not facts.repository
        or not facts.main_ref
        or not _OID_RE.match(facts.main_head or "")
        or not facts.environment_name
    ):
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_REMOTE_FACT_UNAVAILABLE)
    if facts.repository != EXPECTED_REPOSITORY or facts.main_ref != EXPECTED_REF:
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_REPOSITORY_MISMATCH)
    if facts.main_protected is not True:
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_REMOTE_MAIN_NOT_PROTECTED)

    # ── environment 외부 강제 ─────────────────────────────────────────
    if facts.environment_name != EXPECTED_ENVIRONMENT:
        raise WorkflowIdentityError(TRUSTED_ENVIRONMENT_NOT_FOUND)
    if facts.environment_main_only is not True:
        raise WorkflowIdentityError(TRUSTED_ENVIRONMENT_POLICY_MISMATCH)

    # ── 세 좌표가 모두 같아야 한다 ────────────────────────────────────
    if not _OID_RE.match(identity.sha or ""):
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_SHA_NOT_PROTECTED_HEAD)
    # main 이 실행 시작 후 전진하면 fail-closed. 새 main 에서 새 실행을 시작한다.
    if identity.sha != facts.main_head:
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_SHA_NOT_PROTECTED_HEAD)
    if not _OID_RE.match(verifier_commit or "") or verifier_commit != identity.sha:
        raise WorkflowIdentityError(TRUSTED_WORKFLOW_VERIFIER_MISMATCH)


__all__ = [
    "ALLOWED_EVENTS",
    "EXPECTED_ENVIRONMENT",
    "EXPECTED_REF",
    "EXPECTED_REPOSITORY",
    "TRUSTED_ENVIRONMENT_NOT_FOUND",
    "TRUSTED_ENVIRONMENT_POLICY_MISMATCH",
    "TRUSTED_WORKFLOW_EVENT_NOT_ALLOWED",
    "TRUSTED_WORKFLOW_REF_NOT_MAIN",
    "TRUSTED_WORKFLOW_REF_NOT_PROTECTED",
    "TRUSTED_WORKFLOW_REMOTE_FACT_UNAVAILABLE",
    "TRUSTED_WORKFLOW_REMOTE_MAIN_NOT_PROTECTED",
    "TRUSTED_WORKFLOW_REPOSITORY_MISMATCH",
    "TRUSTED_WORKFLOW_SHA_NOT_PROTECTED_HEAD",
    "TRUSTED_WORKFLOW_VERIFIER_MISMATCH",
    "ProtectedFacts",
    "WorkflowIdentity",
    "WorkflowIdentityError",
    "verify_workflow_identity",
]
