"""§6 R6-3 — 단계 B 전 token 사전점검 (의존형 상태기계).

이전 판의 결함(감사 C5)
  · `canonical_requests()` 가 모든 URL 을 ★실행 전에 평평하게★ 만들었다.
    그 결과 `approval_compare("0" * 40)` 처럼 all-zero placeholder 로 주소를
    만들었고, 아직 모르는 후보 head 자리도 자리표로 채웠다.
  · `--approver-login` 을 사람이 주었다. 승인서와 다른 사용자를 검사해도
    통과하는 길이 열려 있었다.
  · 어떤 워크플로도 이 모듈을 부르지 않았다.

이 판의 계약(§6-2)
  S0 CONTEXT_VALIDATED          고정 상수와 GitHub context 만으로 문맥을 확정
  S1 STATIC_FACTS_FETCHED       의존이 없는 여섯 read
  S2 APPROVAL_DOCUMENT_VERIFIED digest 먼저, 통과한 문서만 strict parser 로
  S3 CANDIDATE_PR_VERIFIED      PR 응답의 실제 head 를 잠긴 좌표와 대조
  S4 DEPENDENT_REQUESTS_BUILT   ★검증된 값으로만★ 다음 URL 을 만든다
  S5 DEPENDENT_FACTS_FETCHED    token 별 transport 로 실행
  S6 PREFLIGHT_VERDICT          2xx·스키마·좌표·권한·시간 계약 판정

S2 또는 S3 가 실패하면 S4 이후 요청을 ★한 건도★ 보내지 않는다.
all-zero OID·빈 login·생략 OID 가 URL 에 들어가려 하면 transport 전에 닫는다.

★공개 출력은 정확히 두 줄이고 stderr 는 0 bytes 다. HTTP body·header·token·
  URL query 원문을 출력하지 않는다.
★단계 A 에서는 fake transport 시험만 돈다. 보호 token 실제 실행은 병합 후다.
  그 사실을 PASS 로 적지 않는다(§6-7).
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from enum import Enum

from . import anchors, remote_facts, workflow_identity
from .approval_loader import ApprovalDocumentError, DocumentOrigin, load_approval_document

# ── 상태 (§6-2) ────────────────────────────────────────────────────────
class State(str, Enum):
    CONTEXT_VALIDATED = "S0_CONTEXT_VALIDATED"
    STATIC_FACTS_FETCHED = "S1_STATIC_FACTS_FETCHED"
    APPROVAL_DOCUMENT_VERIFIED = "S2_APPROVAL_DOCUMENT_VERIFIED"
    CANDIDATE_PR_VERIFIED = "S3_CANDIDATE_PR_VERIFIED"
    DEPENDENT_REQUESTS_BUILT = "S4_DEPENDENT_REQUESTS_BUILT"
    DEPENDENT_FACTS_FETCHED = "S5_DEPENDENT_FACTS_FETCHED"
    PREFLIGHT_VERDICT = "S6_PREFLIGHT_VERDICT"


STATE_ORDER = (
    State.CONTEXT_VALIDATED,
    State.STATIC_FACTS_FETCHED,
    State.APPROVAL_DOCUMENT_VERIFIED,
    State.CANDIDATE_PR_VERIFIED,
    State.DEPENDENT_REQUESTS_BUILT,
    State.DEPENDENT_FACTS_FETCHED,
    State.PREFLIGHT_VERDICT,
)

# ── 오류 코드 (§6-4) ───────────────────────────────────────────────────
PREFLIGHT_CONTEXT_INVALID = "PREFLIGHT_CONTEXT_INVALID"
PREFLIGHT_DEPENDENCY_MISSING = "PREFLIGHT_DEPENDENCY_MISSING"
PREFLIGHT_DEPENDENCY_ORDER_VIOLATION = "PREFLIGHT_DEPENDENCY_ORDER_VIOLATION"
PREFLIGHT_PLACEHOLDER_ID_REJECTED = "PREFLIGHT_PLACEHOLDER_ID_REJECTED"
PREFLIGHT_APPROVAL_DIGEST_MISMATCH = "PREFLIGHT_APPROVAL_DIGEST_MISMATCH"
PREFLIGHT_APPROVAL_SCHEMA_INVALID = "PREFLIGHT_APPROVAL_SCHEMA_INVALID"
PREFLIGHT_APPROVER_MISMATCH = "PREFLIGHT_APPROVER_MISMATCH"
PREFLIGHT_CANDIDATE_HEAD_MISMATCH = "PREFLIGHT_CANDIDATE_HEAD_MISMATCH"
PREFLIGHT_URL_NOT_ALLOWED = "PREFLIGHT_URL_NOT_ALLOWED"
PREFLIGHT_REDIRECT_REJECTED = "PREFLIGHT_REDIRECT_REJECTED"
PREFLIGHT_PERMISSION_INSUFFICIENT = "PREFLIGHT_PERMISSION_INSUFFICIENT"
PREFLIGHT_RESPONSE_SCHEMA_INVALID = "PREFLIGHT_RESPONSE_SCHEMA_INVALID"
PREFLIGHT_RUNTIME_NOT_EXECUTED = "PREFLIGHT_RUNTIME_NOT_EXECUTED"

# endpoint 별 read 실패 코드(기존 계약 유지)
PREFLIGHT_APPROVAL_READ_FAILED = "PREFLIGHT_APPROVAL_READ_FAILED"
PREFLIGHT_APPROVAL_ANCESTRY_FAILED = "PREFLIGHT_APPROVAL_ANCESTRY_FAILED"
PREFLIGHT_CANDIDATE_COORD_READ_FAILED = "PREFLIGHT_CANDIDATE_COORD_READ_FAILED"
PREFLIGHT_BRANCH_PROTECTION_READ_FAILED = "PREFLIGHT_BRANCH_PROTECTION_READ_FAILED"
PREFLIGHT_ENVIRONMENT_READ_FAILED = "PREFLIGHT_ENVIRONMENT_READ_FAILED"
PREFLIGHT_BRANCH_POLICY_READ_FAILED = "PREFLIGHT_BRANCH_POLICY_READ_FAILED"
PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED = "PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED"
PREFLIGHT_RUN_FACT_READ_FAILED = "PREFLIGHT_RUN_FACT_READ_FAILED"
PREFLIGHT_APPROVER_READ_FAILED = "PREFLIGHT_APPROVER_READ_FAILED"
PREFLIGHT_TOKEN_ROUTE_VIOLATION = "PREFLIGHT_TOKEN_ROUTE_VIOLATION"
PREFLIGHT_ARGUMENTS_INVALID = "PREFLIGHT_ARGUMENTS_INVALID"
PREFLIGHT_INTERNAL_ERROR = "PREFLIGHT_INTERNAL_ERROR"

# ★승인된 정본은 custom branch policy 로 main 하나다(§G-1).
APPROVED_BRANCH_POLICY_MODE = "custom_branch_policies"
APPROVED_BRANCH_NAME = "main"

_ALL_ZERO_OID = "0" * 40
_ALLOWED_HOSTS = frozenset({"api.github.com"})


@dataclass(frozen=True)
class PlannedRequest:
    """§6-3 — 요청 하나의 계약. token_class 가 붙어야 보낼 수 있다."""

    token_class: remote_facts.Route
    method: str
    host: str
    path: str
    failure_code: str
    schema: str


@dataclass
class PreflightResult:
    ok: bool
    error_code: str
    checked: int = 0
    routes_used: tuple[str, ...] = ()
    reached_state: str = State.CONTEXT_VALIDATED.value
    static_requests: tuple[str, ...] = ()
    dependent_requests: tuple[str, ...] = ()

    @property
    def all_paths(self) -> tuple[str, ...]:
        return self.static_requests + self.dependent_requests


class _Stop(Exception):
    """상태 전이를 멈춘다. 코드만 갖고 다닌다 — raw 를 담지 않는다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _reject_placeholder(*values: str) -> None:
    """§6-2 — 자리표가 URL 로 나가기 전에 닫는다."""
    for value in values:
        if not value or value == _ALL_ZERO_OID or "…" in value or "..." in value:
            raise _Stop(PREFLIGHT_PLACEHOLDER_ID_REJECTED)


def _validate_path(path: str) -> None:
    """§6-3 — allowlist 밖 host·`..`·encoded slash·query token 을 거부한다."""
    if not path or path.startswith(("http://", "https://", "/")):
        # 절대 URL 은 host 를 바꿀 수 있다. 상대 경로만 허용한다.
        raise _Stop(PREFLIGHT_URL_NOT_ALLOWED)
    if "%2f" in path.lower() or "%5c" in path.lower() or "\\" in path:
        raise _Stop(PREFLIGHT_URL_NOT_ALLOWED)
    # `..` 는 ★경로 세그먼트★ 로 판정한다. compare 의 `base...head` 는 한 세그먼트
    # 안의 세 점이므로 traversal 이 아니다. 문자열 포함으로 보면 정상 요청을 막는다.
    for segment in path.partition("?")[0].split("/"):
        if segment in ("", ".", ".."):
            raise _Stop(PREFLIGHT_URL_NOT_ALLOWED)
    if "\n" in path or "\r" in path or " " in path:
        raise _Stop(PREFLIGHT_URL_NOT_ALLOWED)
    query = path.partition("?")[2]
    for forbidden in ("access_token", "token=", "client_secret"):
        if forbidden in query:
            raise _Stop(PREFLIGHT_URL_NOT_ALLOWED)


def _plan(
    route: remote_facts.Route, path: str, failure_code: str, schema: str
) -> PlannedRequest:
    _validate_path(path)
    return PlannedRequest(
        token_class=route, method="GET", host="api.github.com",
        path=path, failure_code=failure_code, schema=schema,
    )


def build_endpoints(
    *, pr_number: int, candidate_head_sha: str, approver_login: str
) -> remote_facts.EndpointBuilder:
    """★production 과 같은 builder 를 만든다. 좌표는 anchors·검증된 응답에서만 온다.

    run_id 는 §6-2 S0 에서 context 로 확정되므로 여기서 받지 않는다.
    """
    return remote_facts.EndpointBuilder(
        approval_repository=anchors.APPROVAL_REPOSITORY,
        approval_protected_ref=anchors.APPROVAL_PROTECTED_REF,
        approval_commit_sha=anchors.APPROVAL_COMMIT_SHA,
        document_path=anchors.APPROVAL_DOCUMENT_PATH,
        signature_path=anchors.APPROVAL_SIGNATURE_PATH,
        allowed_signers_path=anchors.APPROVAL_ALLOWED_SIGNERS_PATH,
        approver_login=approver_login,
        candidate_repository=anchors.CANDIDATE_REPOSITORY,
        pr_number=pr_number,
        candidate_head_sha=candidate_head_sha,
        run_repository=anchors.CANDIDATE_REPOSITORY,
        run_id=0,
        environment_name=workflow_identity.EXPECTED_ENVIRONMENT,
    )


@dataclass
class _Machine:
    """§6-2 상태기계. 앞 응답의 실측 값으로 다음 요청을 만든다."""

    router: remote_facts.TransportRouter
    run_id: int
    locked_candidate_head: str
    locked_candidate_tree: str
    pinned_document_sha256: str = anchors.APPROVAL_DOCUMENT_SHA256
    pr_number: int = anchors.CANDIDATE_PR_NUMBER

    state: State = State.CONTEXT_VALIDATED
    checked: int = 0
    routes_used: list[str] = field(default_factory=list)
    static_paths: list[str] = field(default_factory=list)
    dependent_paths: list[str] = field(default_factory=list)

    # ── 전송 ──────────────────────────────────────────────────────────
    def _send(self, request: PlannedRequest) -> remote_facts.TransportResult:
        if request.host not in _ALLOWED_HOSTS:
            raise _Stop(PREFLIGHT_URL_NOT_ALLOWED)
        derived = remote_facts.route_for(
            request.path,
            approval_repository=anchors.APPROVAL_REPOSITORY,
            candidate_repository=anchors.CANDIDATE_REPOSITORY,
        )
        if derived is not request.token_class:
            raise _Stop(PREFLIGHT_TOKEN_ROUTE_VIOLATION)

        result = self.router.transport_for(request.token_class)(request.path)
        self.checked += 1
        self.routes_used.append(request.token_class.value)

        if 300 <= result.status < 400:
            # ★redirect 자동 추적을 끈다. 따라가면 host allowlist 를 벗어난다.
            raise _Stop(PREFLIGHT_REDIRECT_REJECTED)
        if result.status in (401, 403):
            remaining = str(result.headers.get("x-ratelimit-remaining", "")).strip()
            if result.status == 403 and remaining == "0":
                raise _Stop(request.failure_code)
            raise _Stop(PREFLIGHT_PERMISSION_INSUFFICIENT)
        if remote_facts.classify(result) is not None:
            raise _Stop(request.failure_code)
        if request.schema == "object" and not isinstance(result.payload, dict):
            raise _Stop(PREFLIGHT_RESPONSE_SCHEMA_INVALID)
        return result

    def _static(self, request: PlannedRequest) -> remote_facts.TransportResult:
        self.static_paths.append(request.path)
        return self._send(request)

    def _dependent(self, request: PlannedRequest) -> remote_facts.TransportResult:
        if STATE_ORDER.index(self.state) < STATE_ORDER.index(State.DEPENDENT_REQUESTS_BUILT):
            raise _Stop(PREFLIGHT_DEPENDENCY_ORDER_VIOLATION)
        self.dependent_paths.append(request.path)
        return self._send(request)

    # ── S0 ────────────────────────────────────────────────────────────
    def s0_context(self) -> None:
        if not isinstance(self.run_id, int) or self.run_id <= 0:
            raise _Stop(PREFLIGHT_CONTEXT_INVALID)
        if not anchors.APPROVAL_REPOSITORY or not anchors.CANDIDATE_REPOSITORY:
            raise _Stop(PREFLIGHT_CONTEXT_INVALID)
        _reject_placeholder(self.locked_candidate_head, self.locked_candidate_tree)
        if len(self.pinned_document_sha256) != 64:
            raise _Stop(PREFLIGHT_CONTEXT_INVALID)
        self.state = State.CONTEXT_VALIDATED

    # ── S1 ────────────────────────────────────────────────────────────
    def s1_static(self) -> tuple[dict, dict, bytes, dict, dict]:
        endpoints = build_endpoints(
            pr_number=self.pr_number,
            candidate_head_sha=self.locked_candidate_head,
            approver_login="",  # 아직 모른다. 이 단계에서 쓰지 않는다.
        )
        repo = self._static(_plan(
            remote_facts.Route.APPROVAL, endpoints.approval_repo(),
            PREFLIGHT_APPROVAL_READ_FAILED, "object",
        )).payload
        ref = self._static(_plan(
            remote_facts.Route.APPROVAL, endpoints.approval_ref(),
            PREFLIGHT_APPROVAL_READ_FAILED, "object",
        )).payload
        commit = self._static(_plan(
            remote_facts.Route.APPROVAL, endpoints.approval_commit(),
            PREFLIGHT_APPROVAL_READ_FAILED, "object",
        )).payload
        document = self._static(_plan(
            remote_facts.Route.APPROVAL,
            endpoints.approval_contents(anchors.APPROVAL_DOCUMENT_PATH),
            PREFLIGHT_APPROVAL_READ_FAILED, "object",
        )).payload
        pull = self._static(_plan(
            remote_facts.Route.CANDIDATE, endpoints.candidate_pull(),
            PREFLIGHT_CANDIDATE_COORD_READ_FAILED, "object",
        )).payload
        run = self._static(_plan(
            remote_facts.Route.RUN,
            f"repos/{anchors.CANDIDATE_REPOSITORY}/actions/runs/{self.run_id}",
            PREFLIGHT_RUN_FACT_READ_FAILED, "object",
        )).payload
        environment = self._static(_plan(
            remote_facts.Route.CANDIDATE, endpoints.candidate_environment(),
            PREFLIGHT_ENVIRONMENT_READ_FAILED, "object",
        )).payload

        self.state = State.STATIC_FACTS_FETCHED
        document_bytes = _decode_contents(document)
        if document_bytes is None:
            raise _Stop(PREFLIGHT_APPROVAL_READ_FAILED)
        if not isinstance(run, dict):
            raise _Stop(PREFLIGHT_RUN_FACT_READ_FAILED)
        return ref, commit, document_bytes, pull, environment

    # ── S2 ────────────────────────────────────────────────────────────
    def s2_document(self, *, document_bytes: bytes, ref_payload: dict) -> tuple[str, str]:
        """digest 먼저, 그 다음 parser. 순서를 바꾸면 위조 문서를 파싱하게 된다."""
        measured = hashlib.sha256(document_bytes).hexdigest()
        if measured != self.pinned_document_sha256:
            raise _Stop(PREFLIGHT_APPROVAL_DIGEST_MISMATCH)

        origin = DocumentOrigin(
            repository=anchors.APPROVAL_REPOSITORY,
            protected_ref=anchors.APPROVAL_PROTECTED_REF,
            document_path=anchors.APPROVAL_DOCUMENT_PATH,
            approval_commit_sha=anchors.APPROVAL_COMMIT_SHA,
        )
        try:
            approval = load_approval_document(
                document_bytes, origin=origin,
                pinned_document_sha256=self.pinned_document_sha256,
            )
        except ApprovalDocumentError as exc:
            raise _Stop(PREFLIGHT_APPROVAL_SCHEMA_INVALID) from exc

        obj = ref_payload.get("object") if isinstance(ref_payload, dict) else None
        protected_head = obj.get("sha") if isinstance(obj, dict) else ""
        if not isinstance(protected_head, str):
            protected_head = ""
        _reject_placeholder(protected_head, approval.approver_login)
        if approval.candidate_head_sha != self.locked_candidate_head:
            raise _Stop(PREFLIGHT_APPROVER_MISMATCH)

        self.state = State.APPROVAL_DOCUMENT_VERIFIED
        return protected_head, approval.approver_login

    # ── S3 ────────────────────────────────────────────────────────────
    def s3_candidate(self, pull_payload: dict) -> str:
        head = pull_payload.get("head") if isinstance(pull_payload, dict) else None
        sha = head.get("sha") if isinstance(head, dict) else None
        if not isinstance(sha, str):
            raise _Stop(PREFLIGHT_RESPONSE_SCHEMA_INVALID)
        _reject_placeholder(sha)
        if sha != self.locked_candidate_head:
            raise _Stop(PREFLIGHT_CANDIDATE_HEAD_MISMATCH)
        self.state = State.CANDIDATE_PR_VERIFIED
        return sha

    # ── S4 ────────────────────────────────────────────────────────────
    def s4_build(
        self, *, protected_head: str, candidate_head: str, approver_login: str,
        environment_payload: dict,
    ) -> tuple[PlannedRequest, ...]:
        if self.state is not State.CANDIDATE_PR_VERIFIED:
            raise _Stop(PREFLIGHT_DEPENDENCY_ORDER_VIOLATION)
        _reject_placeholder(protected_head, candidate_head, approver_login)

        endpoints = build_endpoints(
            pr_number=self.pr_number,
            candidate_head_sha=candidate_head,
            approver_login=approver_login,
        )
        planned = [
            _plan(remote_facts.Route.APPROVAL, endpoints.approval_compare(protected_head),
                  PREFLIGHT_APPROVAL_ANCESTRY_FAILED, "object"),
            _plan(remote_facts.Route.APPROVAL,
                  endpoints.approval_contents(anchors.APPROVAL_SIGNATURE_PATH),
                  PREFLIGHT_APPROVAL_READ_FAILED, "object"),
            _plan(remote_facts.Route.APPROVAL,
                  endpoints.approval_contents(anchors.APPROVAL_ALLOWED_SIGNERS_PATH),
                  PREFLIGHT_APPROVAL_READ_FAILED, "object"),
            _plan(remote_facts.Route.APPROVAL, endpoints.approver(),
                  PREFLIGHT_APPROVER_READ_FAILED, "object"),
            _plan(remote_facts.Route.CANDIDATE, endpoints.candidate_commit(candidate_head),
                  PREFLIGHT_CANDIDATE_COORD_READ_FAILED, "object"),
            _plan(remote_facts.Route.CANDIDATE, endpoints.candidate_repo(),
                  PREFLIGHT_CANDIDATE_COORD_READ_FAILED, "object"),
            _plan(remote_facts.Route.CANDIDATE, endpoints.candidate_branch(APPROVED_BRANCH_NAME),
                  PREFLIGHT_BRANCH_PROTECTION_READ_FAILED, "object"),
        ]
        # ★environment 응답에 custom rule 이 있을 때만 그 endpoint 를 만든다(§6-2 S4).
        policy = (
            environment_payload.get("deployment_branch_policy")
            if isinstance(environment_payload, dict) else None
        )
        if not isinstance(policy, dict):
            raise _Stop(PREFLIGHT_ENVIRONMENT_READ_FAILED)
        if policy.get("custom_branch_policies") is not True:
            raise _Stop(PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED)
        planned.append(
            _plan(remote_facts.Route.CANDIDATE, endpoints.candidate_environment_policies(),
                  PREFLIGHT_BRANCH_POLICY_READ_FAILED, "object")
        )
        self.state = State.DEPENDENT_REQUESTS_BUILT
        return tuple(planned)

    # ── S5 · S6 ───────────────────────────────────────────────────────
    def s5_fetch(self, planned: tuple[PlannedRequest, ...]) -> dict[str, object]:
        payloads: dict[str, object] = {}
        for request in planned:
            payloads[request.path] = self._dependent(request).payload
        self.state = State.DEPENDENT_FACTS_FETCHED
        return payloads

    def s6_verdict(self, payloads: dict[str, object]) -> None:
        policies = next(
            (value for path, value in payloads.items()
             if path.endswith("/deployment-branch-policies")),
            None,
        )
        branches = policies.get("branch_policies") if isinstance(policies, dict) else None
        names = (
            [entry.get("name") for entry in branches if isinstance(entry, dict)]
            if isinstance(branches, list) else []
        )
        if names != [APPROVED_BRANCH_NAME]:
            raise _Stop(PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED)
        self.state = State.PREFLIGHT_VERDICT


def _decode_contents(payload: object) -> bytes | None:
    import base64
    import binascii

    if not isinstance(payload, dict):
        return None
    if payload.get("encoding") not in (None, "base64"):
        return None
    content = payload.get("content")
    if not isinstance(content, str):
        return None
    try:
        return base64.b64decode(content, validate=False)
    except (binascii.Error, ValueError):
        return None


def run_preflight(
    *,
    router: remote_facts.TransportRouter,
    run_id: int,
    locked_candidate_head: str,
    locked_candidate_tree: str,
) -> PreflightResult:
    """단계 B 가 실제로 부르는 read 를 ★의존 순서대로★ 확인한다.

    좌표·approver 를 인자로 받지 않는다. 잠긴 좌표와 검증된 승인 문서에서 온다.
    """
    machine = _Machine(
        router=router, run_id=run_id,
        locked_candidate_head=locked_candidate_head,
        locked_candidate_tree=locked_candidate_tree,
    )

    def _result(ok: bool, code: str) -> PreflightResult:
        return PreflightResult(
            ok=ok, error_code=code, checked=machine.checked,
            routes_used=tuple(machine.routes_used),
            reached_state=machine.state.value,
            static_requests=tuple(machine.static_paths),
            dependent_requests=tuple(machine.dependent_paths),
        )

    try:
        machine.s0_context()
        ref, _commit, document_bytes, pull, environment = machine.s1_static()
        protected_head, approver_login = machine.s2_document(
            document_bytes=document_bytes, ref_payload=ref
        )
        candidate_head = machine.s3_candidate(pull)
        planned = machine.s4_build(
            protected_head=protected_head, candidate_head=candidate_head,
            approver_login=approver_login, environment_payload=environment,
        )
        payloads = machine.s5_fetch(planned)
        machine.s6_verdict(payloads)
    except _Stop as stop:
        return _result(False, stop.code)
    except ValueError:
        # route_for 가 허용하지 않은 경로
        return _result(False, PREFLIGHT_TOKEN_ROUTE_VIOLATION)
    return _result(True, "OK")


def _emit(verdict: int, error_code: str) -> None:
    """★정확히 두 줄. stderr 는 0 bytes."""
    print(f"VERDICT={verdict}")
    print(f"ERROR_CODE={error_code}")


def _main(argv: list[str]) -> int:
    """★인자를 받지 않는다(§6-1). run id 는 GitHub context 에서만 온다."""
    if argv:
        _emit(0, PREFLIGHT_ARGUMENTS_INVALID)
        return 1

    import os
    from pathlib import Path

    from . import lock_verifier

    raw_run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not raw_run_id.isdigit() or int(raw_run_id) <= 0:
        _emit(0, PREFLIGHT_CONTEXT_INVALID)
        return 1

    root = Path(__file__).resolve().parents[3]
    try:
        lock = lock_verifier.load_candidate_lock(
            (root / anchors.CANDIDATE_LOCK_PATH).read_bytes()
        )
    except (OSError, lock_verifier.LockSchemaError):
        _emit(0, PREFLIGHT_CONTEXT_INVALID)
        return 1

    router = remote_facts.TransportRouter(
        approval=remote_facts.gh_transport_for(remote_facts.APPROVAL_TOKEN_ENV),
        candidate=remote_facts.gh_transport_for(remote_facts.CANDIDATE_TOKEN_ENV),
        run=remote_facts.gh_transport_for(remote_facts.CANDIDATE_TOKEN_ENV),
    )
    try:
        result = run_preflight(
            router=router,
            run_id=int(raw_run_id),
            locked_candidate_head=lock.approved_head_commit,
            locked_candidate_tree=lock.approved_head_tree,
        )
    except Exception:  # noqa: BLE001 - traceback 을 공개하지 않는다
        _emit(0, PREFLIGHT_INTERNAL_ERROR)
        return 1
    _emit(1 if result.ok else 0, result.error_code)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))


__all__ = [
    "APPROVED_BRANCH_NAME",
    "APPROVED_BRANCH_POLICY_MODE",
    "PREFLIGHT_APPROVAL_ANCESTRY_FAILED",
    "PREFLIGHT_APPROVAL_DIGEST_MISMATCH",
    "PREFLIGHT_APPROVAL_READ_FAILED",
    "PREFLIGHT_APPROVAL_SCHEMA_INVALID",
    "PREFLIGHT_APPROVER_MISMATCH",
    "PREFLIGHT_APPROVER_READ_FAILED",
    "PREFLIGHT_ARGUMENTS_INVALID",
    "PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED",
    "PREFLIGHT_BRANCH_POLICY_READ_FAILED",
    "PREFLIGHT_BRANCH_PROTECTION_READ_FAILED",
    "PREFLIGHT_CANDIDATE_COORD_READ_FAILED",
    "PREFLIGHT_CANDIDATE_HEAD_MISMATCH",
    "PREFLIGHT_CONTEXT_INVALID",
    "PREFLIGHT_DEPENDENCY_MISSING",
    "PREFLIGHT_DEPENDENCY_ORDER_VIOLATION",
    "PREFLIGHT_ENVIRONMENT_READ_FAILED",
    "PREFLIGHT_INTERNAL_ERROR",
    "PREFLIGHT_PERMISSION_INSUFFICIENT",
    "PREFLIGHT_PLACEHOLDER_ID_REJECTED",
    "PREFLIGHT_REDIRECT_REJECTED",
    "PREFLIGHT_RESPONSE_SCHEMA_INVALID",
    "PREFLIGHT_RUNTIME_NOT_EXECUTED",
    "PREFLIGHT_RUN_FACT_READ_FAILED",
    "PREFLIGHT_TOKEN_ROUTE_VIOLATION",
    "PREFLIGHT_URL_NOT_ALLOWED",
    "PlannedRequest",
    "PreflightResult",
    "STATE_ORDER",
    "State",
    "build_endpoints",
    "run_preflight",
]
