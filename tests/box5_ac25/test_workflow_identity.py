"""§15 M-2 — main 신원과 environment 강제 시험.

감사 PRIMARY_BLOCK. "이 워크플로는 main 에서만 돈다" 를 전제로만 두었다.

★workflow context 와 remote facts 를 같은 값에서 복제하지 않는다.
  베끼면 대조가 자기증명이 된다 — 그 자기복제 자체를 시험으로 잡는다.
"""
from __future__ import annotations

import pytest
from ac25 import workflow_identity as wid

pytestmark = pytest.mark.no_sidecar_token

MAIN_HEAD = "3152bb7210b428bdb8f0dec00925a611f86a292f"


def _identity(**overrides) -> wid.WorkflowIdentity:
    values = {
        "event_name": "workflow_dispatch",
        "repository": wid.EXPECTED_REPOSITORY,
        "ref": wid.EXPECTED_REF,
        "ref_protected": True,
        "sha": MAIN_HEAD,
        "run_id": "30983470303",
        "run_attempt": "1",
        "actor_id": "238947383",
    }
    values.update(overrides)
    return wid.WorkflowIdentity(**values)


def _facts(**overrides) -> wid.ProtectedFacts:
    values = {
        "repository": wid.EXPECTED_REPOSITORY,
        "main_ref": wid.EXPECTED_REF,
        "main_head": MAIN_HEAD,
        "main_protected": True,
        "environment_name": wid.EXPECTED_ENVIRONMENT,
        "environment_main_only": True,
    }
    values.update(overrides)
    return wid.ProtectedFacts(**values)


def _verify(identity=None, facts=None, verifier_commit=MAIN_HEAD):
    wid.verify_workflow_identity(
        identity=identity or _identity(),
        facts=facts or _facts(),
        verifier_commit=verifier_commit,
    )


def _code(**kwargs) -> str:
    with pytest.raises(wid.WorkflowIdentityError) as caught:
        _verify(**kwargs)
    return caught.value.code


# ══ 정상 통과 (항상 막는 verifier 는 합격이 아니다) ════════════════════
def test_protected_main_dispatch_passes():
    _verify()


# ══ event·repository·ref 불일치 ════════════════════════════════════════
@pytest.mark.parametrize(
    "event", ["pull_request", "pull_request_target", "push", "workflow_run", "repository_dispatch"]
)
def test_other_events_are_rejected(event):
    assert _code(identity=_identity(event_name=event)) == wid.TRUSTED_WORKFLOW_EVENT_NOT_ALLOWED


def test_only_workflow_dispatch_is_allowed():
    assert wid.ALLOWED_EVENTS == frozenset({"workflow_dispatch"})


def test_repository_mismatch_is_rejected():
    assert (
        _code(identity=_identity(repository="attacker/fork"))
        == wid.TRUSTED_WORKFLOW_REPOSITORY_MISMATCH
    )


@pytest.mark.parametrize("ref", ["refs/heads/feature", "refs/tags/v1", "refs/pull/903/merge"])
def test_non_main_ref_is_rejected(ref):
    assert _code(identity=_identity(ref=ref)) == wid.TRUSTED_WORKFLOW_REF_NOT_MAIN


# ══ context·remote protection false ════════════════════════════════════
def test_context_ref_not_protected_is_rejected():
    assert (
        _code(identity=_identity(ref_protected=False))
        == wid.TRUSTED_WORKFLOW_REF_NOT_PROTECTED
    )


def test_remote_main_not_protected_is_rejected():
    assert (
        _code(facts=_facts(main_protected=False))
        == wid.TRUSTED_WORKFLOW_REMOTE_MAIN_NOT_PROTECTED
    )


def test_context_protected_but_remote_unprotected_still_fails():
    """context 만 참이면 통과시키지 않는다. 러너 값은 신뢰원이 아니다."""
    assert (
        _code(identity=_identity(ref_protected=True), facts=_facts(main_protected=False))
        == wid.TRUSTED_WORKFLOW_REMOTE_MAIN_NOT_PROTECTED
    )


# ══ main head·verifier mismatch ════════════════════════════════════════
def test_main_moved_after_run_start_is_fail_closed():
    """실행 시작 뒤 main 이 전진하면 닫는다. 새 main 에서 새 실행을 시작한다."""
    assert (
        _code(facts=_facts(main_head="f" * 40))
        == wid.TRUSTED_WORKFLOW_SHA_NOT_PROTECTED_HEAD
    )


def test_verifier_commit_mismatch_is_rejected():
    assert _code(verifier_commit="a" * 40) == wid.TRUSTED_WORKFLOW_VERIFIER_MISMATCH


@pytest.mark.parametrize("value", ["", "not-an-oid", MAIN_HEAD.upper()])
def test_malformed_sha_is_rejected(value):
    assert (
        _code(identity=_identity(sha=value)) == wid.TRUSTED_WORKFLOW_SHA_NOT_PROTECTED_HEAD
    )


@pytest.mark.parametrize("value", ["", "not-an-oid"])
def test_malformed_verifier_commit_is_rejected(value):
    assert _code(verifier_commit=value) == wid.TRUSTED_WORKFLOW_VERIFIER_MISMATCH


# ══ environment 부재·정책 불일치 ═══════════════════════════════════════
def test_missing_environment_is_rejected():
    assert _code(facts=_facts(environment_name="")) == (
        wid.TRUSTED_WORKFLOW_REMOTE_FACT_UNAVAILABLE
    )


def test_wrong_environment_name_is_rejected():
    assert (
        _code(facts=_facts(environment_name="some-other-env"))
        == wid.TRUSTED_ENVIRONMENT_NOT_FOUND
    )


def test_environment_allowing_other_branches_is_rejected():
    assert (
        _code(facts=_facts(environment_main_only=False))
        == wid.TRUSTED_ENVIRONMENT_POLICY_MISMATCH
    )


# ══ remote fact 부재 ═══════════════════════════════════════════════════
@pytest.mark.parametrize(
    "override",
    [{"repository": ""}, {"main_ref": ""}, {"main_head": ""}, {"main_head": "short"}],
)
def test_unavailable_remote_fact_is_fail_closed(override):
    assert _code(facts=_facts(**override)) == wid.TRUSTED_WORKFLOW_REMOTE_FACT_UNAVAILABLE


# ══ context 와 remote facts 자기복제 차단 ══════════════════════════════
def test_module_never_builds_facts_from_context():
    """★ProtectedFacts 를 WorkflowIdentity 에서 만들어 내는 코드가 없어야 한다."""
    import inspect

    source = inspect.getsource(wid)
    assert "ProtectedFacts(" not in source.split("class ProtectedFacts")[1].split("def ")[0]
    # 생성 헬퍼가 이 모듈에 없다 — 원격 응답에서만 만들어진다
    assert source.count("ProtectedFacts(") == 0


def test_protected_facts_are_built_only_from_api_responses():
    """read_protected_facts 는 remote_facts 에 있고 transport 응답만 읽는다."""
    import inspect

    from ac25 import remote_facts

    source = inspect.getsource(remote_facts.read_protected_facts)
    assert "reader.object(" in source
    # workflow context 환경변수를 읽는 곳이 없다
    assert "os.environ" not in source
    assert "GITHUB_" not in source


def test_identity_and_facts_are_distinct_types():
    assert wid.WorkflowIdentity is not wid.ProtectedFacts
    assert set(wid.WorkflowIdentity.__dataclass_fields__) != set(
        wid.ProtectedFacts.__dataclass_fields__
    )
