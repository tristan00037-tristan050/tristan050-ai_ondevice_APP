"""§6-6 R6-3 — token 사전점검 의존형 상태기계 시험.

감사 C5 가 지목한 것
  · `approval_compare("0" * 40)` — all-zero 자리표로 주소를 만들었다
  · `--approver-login` — 사람이 준 승인자로 검사했다
  · 아무 워크플로도 이 모듈을 부르지 않았다

이 시험은 셋을 각각 닫혔는지 확인하고, 정상 fake runtime 이 S0→S6 를 실제로
통과하는지도 본다. 막기만 하는 검사기는 합격이 아니다(§3-7).
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest
import yaml
from ac25 import anchors, lock_verifier
from ac25 import remote_facts as rf
from ac25 import token_preflight as tp
from ac25 import workflow_identity

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "box5-ac25-trusted-verification.yml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

DOCUMENT_BYTES = (FIXTURES / "approval_document.md").read_bytes()
DOCUMENT_SHA256 = hashlib.sha256(DOCUMENT_BYTES).hexdigest()

LOCK = lock_verifier.load_candidate_lock(
    (REPO_ROOT / anchors.CANDIDATE_LOCK_PATH).read_bytes()
)
LOCKED_HEAD = LOCK.approved_head_commit
LOCKED_TREE = LOCK.approved_head_tree
PROTECTED_HEAD = "1" * 40
RUN_ID = 31058574141
APPROVER = "tristan00037-tristan050"


CANDIDATE_MAIN_HEAD = "3" * 40   # 후보 저장소 main = 이 run 의 head
APPROVER_ID = 238947383          # 승인 문서가 선언한 값


def _contents(payload: bytes, path: str = anchors.APPROVAL_DOCUMENT_PATH) -> dict:
    """contents 응답. ★path 를 반드시 담는다 — 검증기가 그것을 대조한다(F-01)."""
    return {
        "encoding": "base64",
        "content": base64.b64encode(payload).decode("ascii"),
        "path": path,
    }


def _contents_path_for(url: str) -> str:
    """contents URL 이 어느 파일을 가리키는지 되짚는다(시험용 fake 서버 역할).

    ★접두 일치로 고르면 안 된다 — 서명 경로는 문서 경로 + '.sig' 라서
      문서 경로가 서명 URL 의 접두다. URL 을 실제로 해석한다.
    """
    from urllib.parse import unquote

    encoded = url.partition("/contents/")[2].partition("?")[0]
    return unquote(encoded)


class Recorder:
    """경로별 응답표. 어느 credential 로 왔는지, 몇 번째로 왔는지 기록한다."""

    def __init__(self, name: str, log: list, *, overrides=None) -> None:
        self.name = name
        self.log = log
        self.overrides = overrides or {}

    def __call__(self, path: str) -> rf.TransportResult:
        self.log.append((self.name, path))
        if path in self.overrides:
            return self.overrides[path]
        return _default_response(path)


def _default_response(path: str) -> rf.TransportResult:
    """정상 상태의 fake GitHub 응답.

    ★F-01 이후로는 ★사실이 담긴★ 응답이어야 통과한다. 예전 이 함수는
    `{"ok": True}` 같은 빈 껍데기를 돌려주었고, 그래도 사전점검이 통과했다.
    그것이 감사가 재현한 거짓 통과의 시험 쪽 얼굴이다.
    """
    if path.endswith("/git/ref/heads/main"):
        return rf.TransportResult(
            status=200,
            payload={"ref": "refs/heads/main", "object": {"sha": PROTECTED_HEAD}},
        )
    if "/contents/" in path:
        return rf.TransportResult(
            status=200, payload=_contents(DOCUMENT_BYTES, _contents_path_for(path))
        )
    if path == f"repos/{anchors.CANDIDATE_REPOSITORY}/pulls/{anchors.CANDIDATE_PR_NUMBER}":
        return rf.TransportResult(
            status=200,
            payload={"head": {"sha": LOCKED_HEAD}, "base": {"sha": "2" * 40}},
        )
    if path.endswith("/deployment-branch-policies"):
        return rf.TransportResult(status=200, payload={"branch_policies": [{"name": "main"}]})
    if "/environments/" in path:
        return rf.TransportResult(
            status=200,
            payload={
                "name": workflow_identity.EXPECTED_ENVIRONMENT,
                "deployment_branch_policy": {"custom_branch_policies": True},
            },
        )
    if "/compare/" in path:
        return rf.TransportResult(status=200, payload={"status": "behind"})
    if "/actions/runs/" in path:
        return rf.TransportResult(status=200, payload={
            "id": RUN_ID,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": CANDIDATE_MAIN_HEAD,
            "repository": {"full_name": anchors.CANDIDATE_REPOSITORY},
            "run_started_at": "2026-08-06T00:00:00Z",
        })
    if path.startswith("users/"):
        return rf.TransportResult(
            status=200, payload={"login": APPROVER, "id": APPROVER_ID}
        )
    if "/git/commits/" in path:
        return rf.TransportResult(
            status=200, payload={"sha": LOCKED_HEAD, "tree": {"sha": LOCKED_TREE}}
        )
    if path.endswith("/branches/main"):
        return rf.TransportResult(
            status=200,
            payload={"protected": True, "commit": {"sha": CANDIDATE_MAIN_HEAD}},
        )
    if path == f"repos/{anchors.APPROVAL_REPOSITORY}":
        return rf.TransportResult(
            status=200, payload={"full_name": anchors.APPROVAL_REPOSITORY}
        )
    if path == f"repos/{anchors.CANDIDATE_REPOSITORY}":
        return rf.TransportResult(
            status=200, payload={"full_name": anchors.CANDIDATE_REPOSITORY}
        )
    if "/commits/" in path:  # 승인 커밋
        return rf.TransportResult(status=200, payload={
            "sha": anchors.APPROVAL_COMMIT_SHA,
            "commit": {"committer": {"date": "2026-08-05T04:48:43Z"}},
        })
    return rf.TransportResult(status=200, payload={"ok": True})


def _router(log: list, overrides=None) -> rf.TransportRouter:
    return rf.TransportRouter(
        approval=Recorder("approval", log, overrides=overrides),
        candidate=Recorder("candidate", log, overrides=overrides),
        run=Recorder("run", log, overrides=overrides),
    )


def _run(overrides=None, *, run_id: int = RUN_ID, head: str = LOCKED_HEAD):
    log: list = []
    result = tp.run_preflight(
        router=_router(log, overrides),
        run_id=run_id,
        locked_candidate_head=head,
        locked_candidate_tree=LOCKED_TREE,
    )
    return result, log


def _paths(log: list) -> list[str]:
    return [path for _name, path in log]


@pytest.fixture(autouse=True)
def _pin_document_digest(monkeypatch):
    """픽스처 문서의 지문으로 고정값을 바꿔 fake runtime 을 돌린다.

    ★production 은 anchors 의 고정 지문을 쓴다. 시험만 이 자리를 바꾼다 —
    바꿀 수 있는 자리가 CLI 인자였다면 그것이 C5 의 결함이다.
    """
    monkeypatch.setattr(anchors, "APPROVAL_DOCUMENT_SHA256", DOCUMENT_SHA256)
    monkeypatch.setattr(tp.anchors, "APPROVAL_DOCUMENT_SHA256", DOCUMENT_SHA256)


# ══ §6-6 정상 fake runtime 이 S0→S6 를 통과한다 ════════════════════════
def test_normal_fake_runtime_passes_every_state():
    result, log = _run()
    assert result.ok, result.error_code
    assert result.reached_state == tp.State.PREFLIGHT_VERDICT.value
    assert result.checked == len(log)
    assert result.checked >= 12


# ══ §6-6 all-zero OID 가 어느 경로에도 없다 ════════════════════════════
def test_no_request_path_contains_an_all_zero_oid():
    result, log = _run()
    assert result.ok
    for path in _paths(log):
        assert "0" * 40 not in path, path


def test_placeholder_head_is_rejected_before_any_transport():
    result, log = _run(head="0" * 40)
    assert result.ok is False
    assert result.error_code == tp.PREFLIGHT_PLACEHOLDER_ID_REJECTED
    assert log == [], "자리표인데도 요청을 보냈다"


def test_endpoint_builder_no_longer_exposes_a_flat_url_list():
    """폐기 확인 — 평평한 목록이 있으면 자리표가 다시 들어온다."""
    import ast

    assert not hasattr(rf.EndpointBuilder, "canonical_requests")
    assert hasattr(rf.EndpointBuilder, "static_requests")
    source = (REPO_ROOT / "scripts/ci/ac25/remote_facts.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="remote_facts.py")
    docstrings = {
        ast.get_docstring(node, clean=False) or ""
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
    }
    code = [
        ast.unparse(node) for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    ]
    # ★코드에 all-zero 자리표를 만드는 표현이 없다(설명문에는 있어도 된다)
    assert not any('"0" * 40' in item or "'0' * 40" in item for item in code)
    assert any("자리표" in text for text in docstrings), "폐기 근거가 문서화돼 있지 않다"


def test_static_requests_have_no_dependent_endpoints():
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER,
        candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    paths = [path for _route, path in builder.static_requests()]
    for forbidden in ("/compare/", "users/", "/git/commits/"):
        assert not any(forbidden in path for path in paths), forbidden


# ══ §6-6 의존 순서 ═════════════════════════════════════════════════════
def test_compare_is_not_called_before_the_protected_ref_is_read():
    _result, log = _run()
    paths = _paths(log)
    ref_index = next(i for i, p in enumerate(paths) if p.endswith("/git/ref/heads/main"))
    compare_index = next(i for i, p in enumerate(paths) if "/compare/" in p)
    assert ref_index < compare_index


def test_candidate_commit_is_not_called_before_the_pr_is_verified():
    _result, log = _run()
    paths = _paths(log)
    pull_index = next(i for i, p in enumerate(paths) if p.endswith(f"/pulls/{anchors.CANDIDATE_PR_NUMBER}"))
    commit_index = next(i for i, p in enumerate(paths) if "/git/commits/" in p)
    assert pull_index < commit_index


def test_approver_endpoint_is_not_called_before_the_document_is_verified():
    _result, log = _run()
    paths = _paths(log)
    document_index = next(i for i, p in enumerate(paths) if "/contents/" in p)
    approver_index = next(i for i, p in enumerate(paths) if p.startswith("users/"))
    assert document_index < approver_index


def test_digest_mismatch_stops_before_any_dependent_request():
    """문서 지문이 어긋나면 S4 이후 요청이 0 건이다."""
    tampered = DOCUMENT_BYTES + b"\n<!-- tampered -->\n"
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {
        builder.approval_contents(anchors.APPROVAL_DOCUMENT_PATH):
            rf.TransportResult(status=200, payload=_contents(tampered)),
    }
    result, log = _run(override)
    assert result.ok is False
    assert result.error_code == tp.PREFLIGHT_APPROVAL_DIGEST_MISMATCH
    assert result.dependent_requests == ()
    assert not any("/compare/" in path for path in _paths(log))
    assert not any(path.startswith("users/") for path in _paths(log))


def test_candidate_head_mismatch_stops_before_any_dependent_request():
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {
        builder.candidate_pull(): rf.TransportResult(
            status=200, payload={"head": {"sha": "9" * 40}, "base": {"sha": "2" * 40}}
        ),
    }
    result, log = _run(override)
    assert result.ok is False
    assert result.error_code == tp.PREFLIGHT_CANDIDATE_HEAD_MISMATCH
    assert result.dependent_requests == ()
    assert not any("/compare/" in path for path in _paths(log))


def test_malformed_preceding_response_sends_no_further_transport():
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {
        builder.approval_ref(): rf.TransportResult(status=200, payload=None),
    }
    result, log = _run(override)
    assert result.ok is False
    assert result.dependent_requests == ()
    # ref 까지만 부르고 멈춘다
    assert not any("/compare/" in path for path in _paths(log))


# ══ §6-6 사용자 제공 승인자 경로가 없다 ════════════════════════════════
def test_cli_accepts_no_arguments_at_all():
    assert tp._main(["--approver-login", "attacker"]) == 1
    assert tp._main(["--candidate-head-sha", "f" * 40]) == 1
    assert tp._main(["--run-id", "5"]) == 1


def test_no_approver_or_coordinate_input_exists_in_the_module():
    """CLI 인자 파서 자체가 없어야 한다. 설명문에 옛 인자 이름이 남는 것은 기록이다."""
    import ast

    source = (REPO_ROOT / "scripts/ci/ac25/token_preflight.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="token_preflight.py")
    calls = [ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Call)]
    for forbidden in ("add_argument", "ArgumentParser", "parse_args"):
        assert not any(forbidden in call for call in calls), forbidden
    imported = {
        alias.name for node in ast.walk(tree)
        if isinstance(node, ast.Import) for alias in node.names
    }
    assert "argparse" not in imported


def test_run_preflight_takes_no_approver_argument():
    import inspect

    parameters = set(inspect.signature(tp.run_preflight).parameters)
    assert parameters == {
        "router", "run_id", "locked_candidate_head", "locked_candidate_tree",
    }


def test_approver_comes_from_the_verified_document():
    """승인자 URL 은 ★문서에서 읽은★ login 으로 만들어진다."""
    _result, log = _run()
    approver_paths = [path for path in _paths(log) if path.startswith("users/")]
    assert approver_paths == [f"users/{APPROVER}"]


# ══ §6-6 URL 안전성 ════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example.com/repos/x",
        "repos/../../etc/passwd",
        "repos/a%2Fb/contents/x",
        "repos/x?access_token=abc",
        "/repos/absolute",
        "repos/x y",
    ],
)
def test_unsafe_paths_are_rejected_before_transport(path):
    with pytest.raises(tp._Stop) as caught:
        tp._plan(rf.Route.APPROVAL, path, tp.PREFLIGHT_APPROVAL_READ_FAILED, "object")
    assert caught.value.code == tp.PREFLIGHT_URL_NOT_ALLOWED


def test_redirect_is_rejected():
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {builder.approval_repo(): rf.TransportResult(status=302)}
    result, _log = _run(override)
    assert result.error_code == tp.PREFLIGHT_REDIRECT_REJECTED


def test_cross_route_request_is_refused():
    with pytest.raises(ValueError):
        rf.route_for(
            "repos/attacker/repo/contents/secret",
            approval_repository=anchors.APPROVAL_REPOSITORY,
            candidate_repository=anchors.CANDIDATE_REPOSITORY,
        )


# ══ §6-6 token 경로 분리 ═══════════════════════════════════════════════
def test_each_token_class_sees_only_its_own_endpoints():
    _result, log = _run()
    approval = [path for name, path in log if name == "approval"]
    candidate = [path for name, path in log if name == "candidate"]
    run = [path for name, path in log if name == "run"]

    assert approval and candidate and run
    assert not any(anchors.CANDIDATE_REPOSITORY in path for path in approval)
    assert not any(anchors.APPROVAL_REPOSITORY in path for path in candidate)
    assert not any(anchors.APPROVAL_REPOSITORY in path for path in run)
    assert all("/actions/" in path for path in run)


# ══ §6-6 상태 코드 fail-closed ═════════════════════════════════════════
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, tp.PREFLIGHT_PERMISSION_INSUFFICIENT),
        (403, tp.PREFLIGHT_PERMISSION_INSUFFICIENT),
        (404, tp.PREFLIGHT_APPROVAL_READ_FAILED),
        (429, tp.PREFLIGHT_APPROVAL_READ_FAILED),
        (500, tp.PREFLIGHT_APPROVAL_READ_FAILED),
        (0, tp.PREFLIGHT_APPROVAL_READ_FAILED),
    ],
)
def test_status_failures_are_fail_closed(status, expected):
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {builder.approval_repo(): rf.TransportResult(status=status)}
    result, _log = _run(override)
    assert result.ok is False
    assert result.error_code == expected


def test_rate_limited_403_keeps_the_endpoint_code():
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {
        builder.approval_repo(): rf.TransportResult(
            status=403, headers={"x-ratelimit-remaining": "0"}
        )
    }
    result, _log = _run(override)
    assert result.error_code == tp.PREFLIGHT_APPROVAL_READ_FAILED


def test_truncated_json_is_fail_closed():
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {
        builder.approval_repo(): rf.TransportResult(
            status=200, message="TRANSPORT_BODY_NOT_JSON"
        )
    }
    result, _log = _run(override)
    assert result.ok is False


def test_list_response_where_an_object_is_required_is_rejected():
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {builder.approval_repo(): rf.TransportResult(status=200, payload=[])}
    result, _log = _run(override)
    assert result.error_code == tp.PREFLIGHT_RESPONSE_SCHEMA_INVALID


def test_invalid_run_id_is_context_invalid():
    result, log = _run(run_id=0)
    assert result.error_code == tp.PREFLIGHT_CONTEXT_INVALID
    assert log == []


# ══ §6-6 environment·branch 정책 ═══════════════════════════════════════
def test_non_custom_branch_policy_mode_is_unapproved():
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {
        builder.candidate_environment(): rf.TransportResult(
            status=200,
            payload={
                "name": workflow_identity.EXPECTED_ENVIRONMENT,
                "deployment_branch_policy": {"custom_branch_policies": False},
            },
        )
    }
    result, log = _run(override)
    assert result.error_code == tp.PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED
    # ★모드가 정본이 아니면 정책 endpoint 를 아예 만들지 않는다(§6-2 S4)
    assert not any(path.endswith("/deployment-branch-policies") for path in _paths(log))


@pytest.mark.parametrize(
    "branches",
    [[], [{"name": "main"}, {"name": "release"}], [{"name": "release"}], "notalist"],
)
def test_branch_policy_other_than_main_only_is_unapproved(branches):
    builder = tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER, candidate_head_sha=LOCKED_HEAD,
        approver_login="",
    )
    override = {
        builder.candidate_environment_policies(): rf.TransportResult(
            status=200, payload={"branch_policies": branches}
        )
    }
    result, _log = _run(override)
    assert result.error_code == tp.PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED


# ══ §6-6 공개 출력 ═════════════════════════════════════════════════════
def test_cli_emits_exactly_two_lines(capsys, monkeypatch):
    monkeypatch.setattr(tp, "run_preflight", lambda **_kwargs: tp.PreflightResult(
        False, tp.PREFLIGHT_ENVIRONMENT_READ_FAILED, 3, ("approval",)
    ))
    monkeypatch.setenv("GITHUB_RUN_ID", str(RUN_ID))
    assert tp._main([]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "VERDICT=0", f"ERROR_CODE={tp.PREFLIGHT_ENVIRONMENT_READ_FAILED}"
    ]
    assert captured.err == ""


def test_cli_never_prints_arguments(capsys):
    assert tp._main(["$(id)"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "$(id)" not in captured.out
    assert captured.out.splitlines() == [
        "VERDICT=0", f"ERROR_CODE={tp.PREFLIGHT_ARGUMENTS_INVALID}"
    ]


def test_module_never_prints_raw_response_fields():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(tp))
    printed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
            printed.append(ast.unparse(node))
    assert printed, "출력이 하나도 없다"
    for statement in printed:
        assert "VERDICT=" in statement or "ERROR_CODE=" in statement, statement
        for forbidden in ("payload", "headers", "result.", "response", "token"):
            assert forbidden not in statement, statement


# ══ §6-6 워크플로 배선 ═════════════════════════════════════════════════
def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_has_a_token_preflight_job():
    workflow = _workflow()
    job = workflow["jobs"]["token-preflight"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["environment"] == "ac25-trusted-main"
    assert job["permissions"] == {"actions": "read", "contents": "read"}
    run_bodies = "\n".join(step.get("run", "") for step in job["steps"])
    assert "ac25.token_preflight" in run_bodies


def test_every_verification_job_needs_the_preflight():
    workflow = _workflow()
    for name in ("trusted-verification", "candidate-lane", "integration-lane"):
        needs = workflow["jobs"][name]["needs"]
        needs = [needs] if isinstance(needs, str) else needs
        assert "token-preflight" in needs, name


def test_publish_check_needs_all_four_and_compares_results_explicitly():
    workflow = _workflow()
    publish = workflow["jobs"]["publish-check"]
    assert set(publish["needs"]) == {
        "token-preflight", "trusted-verification", "candidate-lane", "integration-lane",
    }
    assert publish["if"].strip() == "${{ always() }}"
    gate = next(step for step in publish["steps"] if step.get("id") == "gate")
    body = gate["run"]
    assert '!= "success"' in body
    for key in ("PREFLIGHT_RESULT", "TRUSTED_RESULT", "CANDIDATE_RESULT", "INTEGRATION_RESULT"):
        assert key in gate["env"], key


def test_publish_check_does_not_count_a_skipped_preflight_as_pass():
    """workflow 가 결과를 넘기고, publish 모듈이 success 외를 전부 실패로 센다."""
    workflow = _workflow()
    publish = workflow["jobs"]["publish-check"]
    script_step = next(step for step in publish["steps"] if "script" in step.get("with", {}))
    assert script_step["env"]["AC25_PREFLIGHT_RESULT"] == "${{ needs.token-preflight.result }}"
    module = (REPO_ROOT / "scripts/ci/ac25/publish_check.mjs").read_text(encoding="utf-8")
    assert "AC25_PREFLIGHT_RESULT" in module
    assert "PREFLIGHT_JOB_NOT_SUCCESS" in module


def test_preflight_job_uses_two_separate_tokens():
    job = _workflow()["jobs"]["token-preflight"]
    step = next(step for step in job["steps"] if "ac25.token_preflight" in step.get("run", ""))
    assert step["env"]["AC25_APPROVAL_TOKEN"].strip()
    assert step["env"]["AC25_CANDIDATE_TOKEN"].strip()
    assert "GH_TOKEN" not in step["env"]


def test_workflow_dispatch_is_still_the_only_trigger():
    workflow = _workflow()
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert triggers == {"workflow_dispatch": None}


# ══ §6-7 상태를 정직하게 기록한다 ══════════════════════════════════════
def test_protected_runtime_is_not_claimed_anywhere_in_the_repo():
    """보호 token 실제 실행을 PASS 로 적은 곳이 없어야 한다(§6-7 · §H)."""
    for path in sorted((REPO_ROOT / ".github" / "workflows").glob("box5-ac25-*.yml")):
        body = path.read_text(encoding="utf-8")
        assert "TOKEN_PREFLIGHT_PROTECTED_RUNTIME=PASS" not in body, path.name
