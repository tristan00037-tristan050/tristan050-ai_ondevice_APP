"""§20 C5 — token 경로와 사전점검 시험.

★preflight 가 production endpoint 집합을 ★손으로 복제하지 않는다★ 는 것을
  같은 builder 를 쓰는지로 확인한다. "API 네 개만 확인" 은 실제 호출망을 보장하지
  못한다.
★승인 token 으로 후보 저장소를, GITHUB_TOKEN 으로 승인 문서를 만지지 못한다.
"""
from __future__ import annotations

import pytest
from ac25 import anchors, remote_facts as rf, token_preflight as tp, workflow_identity

pytestmark = pytest.mark.no_sidecar_token

APPROVER = "tristan00037-tristan050"


def _endpoints() -> rf.EndpointBuilder:
    return tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER,
        candidate_head_sha="6" * 40,
        run_id=77,
        approver_login=APPROVER,
    )


class Recorder:
    """경로별 응답표. 어느 credential 로 왔는지 기록한다."""

    def __init__(self, name: str, seen: dict, *, overrides=None) -> None:
        self.name = name
        self.seen = seen
        self.overrides = overrides or {}

    def __call__(self, path: str) -> rf.TransportResult:
        self.seen.setdefault(self.name, []).append(path)
        if path in self.overrides:
            return self.overrides[path]
        endpoints = _endpoints()
        if path == endpoints.candidate_environment():
            return rf.TransportResult(
                status=200,
                payload={
                    "name": workflow_identity.EXPECTED_ENVIRONMENT,
                    "deployment_branch_policy": {"custom_branch_policies": True},
                },
            )
        if path == endpoints.candidate_environment_policies():
            return rf.TransportResult(
                status=200, payload={"branch_policies": [{"name": "main"}]}
            )
        return rf.TransportResult(status=200, payload={"ok": True})


def _router(seen: dict, overrides=None) -> rf.TransportRouter:
    return rf.TransportRouter(
        approval=Recorder("approval", seen, overrides=overrides),
        candidate=Recorder("candidate", seen, overrides=overrides),
        run=Recorder("run", seen, overrides=overrides),
    )


# ══ endpoint 집합이 production 과 같다 ═════════════════════════════════
def test_preflight_reuses_the_production_endpoint_builder():
    assert tp.build_endpoints.__module__ == "ac25.token_preflight"
    assert isinstance(_endpoints(), rf.EndpointBuilder)


def test_endpoint_set_covers_every_documented_read():
    paths = [path for _route, path in _endpoints().canonical_requests()]
    joined = "\n".join(paths)
    for fragment in (
        "/git/ref/heads/main", "/commits/", "/compare/", "/contents/",
        "/pulls/", "/git/commits/", "/branches/main",
        "/environments/", "/deployment-branch-policies", "/actions/runs/",
        "users/",
    ):
        assert fragment in joined, fragment
    assert len(paths) == 15


def test_preflight_visits_every_canonical_request():
    seen: dict = {}
    result = tp.run_preflight(router=_router(seen), endpoints=_endpoints())
    assert result.ok, result.error_code
    assert result.checked == len(_endpoints().canonical_requests())
    visited = sum(len(v) for v in seen.values())
    assert visited == result.checked


# ══ 경로 분리 ══════════════════════════════════════════════════════════
def test_each_route_sees_only_its_own_endpoints():
    seen: dict = {}
    tp.run_preflight(router=_router(seen), endpoints=_endpoints())
    approval = seen.get("approval", [])
    candidate = seen.get("candidate", [])
    run = seen.get("run", [])

    assert approval, "승인 경로가 하나도 안 불렸다"
    assert candidate, "후보 경로가 하나도 안 불렸다"
    assert run, "run 경로가 하나도 안 불렸다"

    # ★승인 token 이 후보 저장소를 만지지 않는다
    assert not any(anchors.CANDIDATE_REPOSITORY in p for p in approval)
    # ★후보 token 이 승인 저장소를 읽지 않는다
    assert not any(anchors.APPROVAL_REPOSITORY in p for p in candidate)
    assert not any(anchors.APPROVAL_REPOSITORY in p for p in run)
    assert all("/actions/" in p for p in run)


def test_cross_route_request_is_refused():
    """builder 가 아닌 경로가 섞이면 호출 전에 닫는다."""
    with pytest.raises(ValueError):
        rf.route_for(
            "repos/attacker/repo/contents/secret",
            approval_repository=anchors.APPROVAL_REPOSITORY,
            candidate_repository=anchors.CANDIDATE_REPOSITORY,
        )


# ══ 실패 코드 ══════════════════════════════════════════════════════════
@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_status_failures_are_fail_closed(status):
    endpoints = _endpoints()
    seen: dict = {}
    router = _router(seen, overrides={endpoints.approval_repo(): rf.TransportResult(status=status)})
    result = tp.run_preflight(router=router, endpoints=endpoints)
    assert result.ok is False
    assert result.error_code == tp.PREFLIGHT_APPROVAL_READ_FAILED


def test_malformed_body_is_fail_closed():
    endpoints = _endpoints()
    seen: dict = {}
    router = _router(
        seen, overrides={endpoints.approval_ref(): rf.TransportResult(status=200, payload=None)}
    )
    result = tp.run_preflight(router=router, endpoints=endpoints)
    assert result.ok is False
    assert result.error_code == tp.PREFLIGHT_APPROVAL_READ_FAILED


@pytest.mark.parametrize(
    ("selector", "code"),
    [
        ("approval_compare", tp.PREFLIGHT_APPROVAL_ANCESTRY_FAILED),
        ("approver", tp.PREFLIGHT_APPROVER_READ_FAILED),
        ("candidate_pull", tp.PREFLIGHT_CANDIDATE_COORD_READ_FAILED),
        ("candidate_branch", tp.PREFLIGHT_BRANCH_PROTECTION_READ_FAILED),
        ("candidate_environment", tp.PREFLIGHT_ENVIRONMENT_READ_FAILED),
        ("candidate_environment_policies", tp.PREFLIGHT_BRANCH_POLICY_READ_FAILED),
        ("run_facts", tp.PREFLIGHT_RUN_FACT_READ_FAILED),
    ],
)
def test_each_endpoint_has_its_own_failure_code(selector, code):
    endpoints = _endpoints()
    path = {
        "approval_compare": endpoints.approval_compare("0" * 40),
        "approver": endpoints.approver(),
        "candidate_pull": endpoints.candidate_pull(),
        "candidate_branch": endpoints.candidate_branch("main"),
        "candidate_environment": endpoints.candidate_environment(),
        "candidate_environment_policies": endpoints.candidate_environment_policies(),
        "run_facts": endpoints.run_facts(),
    }[selector]
    seen: dict = {}
    router = _router(seen, overrides={path: rf.TransportResult(status=404)})
    result = tp.run_preflight(router=router, endpoints=endpoints)
    assert result.ok is False
    assert result.error_code == code


# ══ branch policy 모드 ═════════════════════════════════════════════════
def test_non_custom_branch_policy_mode_is_unapproved():
    """★어떤 모드가 정본인지 모르면 억지로 성공시키지 않는다."""
    endpoints = _endpoints()
    seen: dict = {}
    router = _router(seen, overrides={
        endpoints.candidate_environment(): rf.TransportResult(
            status=200,
            payload={"name": "ac25-trusted-main",
                     "deployment_branch_policy": {"custom_branch_policies": False}},
        )
    })
    result = tp.run_preflight(router=router, endpoints=endpoints)
    assert result.error_code == tp.PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED


def test_missing_branch_policy_object_is_environment_failure():
    endpoints = _endpoints()
    seen: dict = {}
    router = _router(seen, overrides={
        endpoints.candidate_environment(): rf.TransportResult(
            status=200, payload={"name": "ac25-trusted-main"}
        )
    })
    result = tp.run_preflight(router=router, endpoints=endpoints)
    assert result.error_code == tp.PREFLIGHT_ENVIRONMENT_READ_FAILED


@pytest.mark.parametrize(
    "branches",
    [[], [{"name": "main"}, {"name": "release"}], [{"name": "release"}], "notalist"],
)
def test_branch_policy_other_than_main_only_is_unapproved(branches):
    endpoints = _endpoints()
    seen: dict = {}
    router = _router(seen, overrides={
        endpoints.candidate_environment_policies(): rf.TransportResult(
            status=200, payload={"branch_policies": branches}
        )
    })
    result = tp.run_preflight(router=router, endpoints=endpoints)
    assert result.error_code == tp.PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED


# ══ 공개 출력 ══════════════════════════════════════════════════════════
def test_cli_emits_exactly_two_lines(capsys, monkeypatch):
    monkeypatch.setattr(tp, "run_preflight", lambda **_kwargs: tp.PreflightResult(
        False, tp.PREFLIGHT_ENVIRONMENT_READ_FAILED, 3, ("approval",)
    ))
    assert tp._main(["--run-id", "5", "--approver-login", APPROVER]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "VERDICT=0", f"ERROR_CODE={tp.PREFLIGHT_ENVIRONMENT_READ_FAILED}"
    ]
    assert captured.err == ""


def test_cli_never_prints_arguments(capsys):
    assert tp._main(["--bogus", "$(id)"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "$(id)" not in captured.out
    assert captured.out.splitlines() == ["VERDICT=0", "ERROR_CODE=PREFLIGHT_ARGUMENTS_INVALID"]


def test_module_never_prints_raw_response_fields():
    """payload 를 ★검사★ 하는 것은 되고, ★출력★ 하는 것은 안 된다."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(tp))
    printed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
            printed.append(ast.unparse(node))
    assert printed, "출력이 하나도 없다"
    for statement in printed:
        # 허용되는 것은 VERDICT·ERROR_CODE 두 줄뿐이다
        assert "VERDICT=" in statement or "ERROR_CODE=" in statement, statement
        for forbidden in ("payload", "headers", "result.", "response", "token"):
            assert forbidden not in statement, statement


# ══ 단계 A 에서는 실행하지 않는다 ══════════════════════════════════════
def test_no_workflow_runs_the_preflight_yet():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / ".github" / "workflows"
    for path in sorted(root.glob("box5-ac25-*.yml")):
        assert "token_preflight" not in path.read_text(encoding="utf-8"), path.name
