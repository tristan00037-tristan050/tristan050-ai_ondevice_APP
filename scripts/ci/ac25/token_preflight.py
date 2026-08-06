"""§15 C5 — 단계 B 전 token 사전점검.

★production 과 ★같은★ endpoint builder·router 를 쓴다. 목록을 손으로 복제하면
  실제 호출망을 보장하지 못한다 — "API 네 개만 확인" 은 그 병이다.

★공개 출력은 정확히 두 줄이고 stderr 는 0 bytes 다. HTTP body·header·token·
  URL query 원문을 출력하지 않는다.

단계 A 에서는 module 과 fake transport 시험만 만든다. 실제 실행은 병합 후
총괄 지시에 따른다.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from . import anchors, remote_facts, workflow_identity

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

# ★승인된 정본은 custom branch policy 로 main 하나다(§G-1).
APPROVED_BRANCH_POLICY_MODE = "custom_branch_policies"
APPROVED_BRANCH_NAME = "main"


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    error_code: str
    checked: int
    routes_used: tuple[str, ...]


def build_endpoints(
    *, pr_number: int, candidate_head_sha: str, run_id: int, approver_login: str
) -> remote_facts.EndpointBuilder:
    """★production 과 같은 builder 를 만든다. 좌표는 anchors 에서만 온다."""
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
        run_id=run_id,
        environment_name=workflow_identity.EXPECTED_ENVIRONMENT,
    )


# endpoint 종류별 실패 코드. builder 목록과 1:1 로 붙는다.
def _code_for(path: str, builder: remote_facts.EndpointBuilder) -> str:
    if path == builder.approver():
        return PREFLIGHT_APPROVER_READ_FAILED
    if path.startswith(f"repos/{builder.approval_repository}/compare/"):
        return PREFLIGHT_APPROVAL_ANCESTRY_FAILED
    if path.startswith(f"repos/{builder.approval_repository}"):
        return PREFLIGHT_APPROVAL_READ_FAILED
    if path.endswith("/deployment-branch-policies"):
        return PREFLIGHT_BRANCH_POLICY_READ_FAILED
    if "/environments/" in path:
        return PREFLIGHT_ENVIRONMENT_READ_FAILED
    if "/branches/" in path:
        return PREFLIGHT_BRANCH_PROTECTION_READ_FAILED
    if "/actions/runs/" in path:
        return PREFLIGHT_RUN_FACT_READ_FAILED
    return PREFLIGHT_CANDIDATE_COORD_READ_FAILED


def _branch_policy_mode_ok(payload: object) -> bool | None:
    """환경 응답의 branch policy 모드가 승인된 정본인지 본다.

    custom_branch_policies=True 일 때만 목록에서 main 하나를 요구한다.
    False 이면 억지로 성공시키지 않고 ★승인되지 않은 모드★ 로 닫는다.
    """
    if not isinstance(payload, dict):
        return None
    policy = payload.get("deployment_branch_policy")
    if not isinstance(policy, dict):
        return None
    return policy.get("custom_branch_policies") is True


def run_preflight(
    *,
    router: remote_facts.TransportRouter,
    endpoints: remote_facts.EndpointBuilder,
) -> PreflightResult:
    """단계 B 가 실제로 부르는 read 를 ★전부★ 사전 확인한다."""
    routes_used: list[str] = []
    checked = 0

    for route, path in endpoints.canonical_requests():
        try:
            derived = remote_facts.route_for(
                path,
                approval_repository=endpoints.approval_repository,
                candidate_repository=endpoints.candidate_repository,
            )
        except ValueError:
            return PreflightResult(False, PREFLIGHT_TOKEN_ROUTE_VIOLATION, checked, tuple(routes_used))
        if derived is not route:
            return PreflightResult(False, PREFLIGHT_TOKEN_ROUTE_VIOLATION, checked, tuple(routes_used))

        result = router.transport_for(route)(path)
        routes_used.append(route.value)
        checked += 1

        if remote_facts.classify(result) is not None:
            return PreflightResult(False, _code_for(path, endpoints), checked, tuple(routes_used))

        if path == endpoints.candidate_environment():
            mode_ok = _branch_policy_mode_ok(result.payload)
            if mode_ok is None:
                return PreflightResult(
                    False, PREFLIGHT_ENVIRONMENT_READ_FAILED, checked, tuple(routes_used)
                )
            if mode_ok is False:
                # 어떤 모드가 정본인지 모르면 통과시키지 않는다
                return PreflightResult(
                    False, PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED, checked, tuple(routes_used)
                )

        if path == endpoints.candidate_environment_policies():
            payload = result.payload
            branches = payload.get("branch_policies") if isinstance(payload, dict) else None
            names = (
                [entry.get("name") for entry in branches if isinstance(entry, dict)]
                if isinstance(branches, list)
                else []
            )
            if names != [APPROVED_BRANCH_NAME]:
                return PreflightResult(
                    False, PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED, checked, tuple(routes_used)
                )

    return PreflightResult(True, "OK", checked, tuple(routes_used))


def _emit(verdict: int, error_code: str) -> None:
    """★정확히 두 줄. stderr 는 0 bytes."""
    print(f"VERDICT={verdict}")
    print(f"ERROR_CODE={error_code}")


class _QuietParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D102
        raise _CliArgumentError()

    def exit(self, status: int = 0, message: str | None = None) -> None:  # noqa: D102
        if status != 0:
            raise _CliArgumentError()
        raise SystemExit(status)


class _CliArgumentError(Exception):
    pass


def _main(argv: list[str]) -> int:
    parser = _QuietParser(description="AC-25 token preflight", add_help=False)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--approver-login", required=True)
    try:
        args = parser.parse_args(argv)
    except _CliArgumentError:
        _emit(0, "PREFLIGHT_ARGUMENTS_INVALID")
        return 1

    endpoints = build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER,
        candidate_head_sha="0" * 40,
        run_id=args.run_id,
        approver_login=args.approver_login,
    )
    router = remote_facts.TransportRouter(
        approval=remote_facts.gh_transport_for(remote_facts.APPROVAL_TOKEN_ENV),
        candidate=remote_facts.gh_transport_for(remote_facts.CANDIDATE_TOKEN_ENV),
        run=remote_facts.gh_transport_for(remote_facts.CANDIDATE_TOKEN_ENV),
    )
    try:
        result = run_preflight(router=router, endpoints=endpoints)
    except Exception:  # noqa: BLE001 - traceback 을 공개하지 않는다
        _emit(0, "PREFLIGHT_INTERNAL_ERROR")
        return 1
    _emit(1 if result.ok else 0, result.error_code)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))


__all__ = [
    "APPROVED_BRANCH_NAME",
    "APPROVED_BRANCH_POLICY_MODE",
    "PREFLIGHT_APPROVAL_ANCESTRY_FAILED",
    "PREFLIGHT_APPROVAL_READ_FAILED",
    "PREFLIGHT_APPROVER_READ_FAILED",
    "PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED",
    "PREFLIGHT_BRANCH_POLICY_READ_FAILED",
    "PREFLIGHT_BRANCH_PROTECTION_READ_FAILED",
    "PREFLIGHT_CANDIDATE_COORD_READ_FAILED",
    "PREFLIGHT_ENVIRONMENT_READ_FAILED",
    "PREFLIGHT_RUN_FACT_READ_FAILED",
    "PREFLIGHT_TOKEN_ROUTE_VIOLATION",
    "PreflightResult",
    "build_endpoints",
    "run_preflight",
]
