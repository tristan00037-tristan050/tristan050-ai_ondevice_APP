"""§15 M-4 — workflow 입력 strict 검증 시험.

허용 형태만 통과시킨다. 위험 문자를 지우는 방식이 아니다 — 지우는 방식은 새
우회가 나올 때마다 뚫린다.
"""
from __future__ import annotations

import pytest
from ac25 import workflow_inputs as wi

pytestmark = pytest.mark.no_sidecar_token

HEAD = "61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd04"
TREE = "313f40cf35b3ee2bf7bcdd946dea9c2e1c4896c2"


def _validate(**overrides):
    values = {
        "pr_number": "903",
        "expected_head": HEAD,
        "expected_tree": TREE,
        "run_id": "30983470303",
        "repository": wi.EXPECTED_REPOSITORY,
        "ref": wi.EXPECTED_REF,
        "event_name": "workflow_dispatch",
        "locked_head": HEAD,
        "locked_tree": TREE,
    }
    values.update(overrides)
    return wi.validate_dispatch_inputs(**values)


# ══ 정상 통과 (항상 막는 검증기는 합격이 아니다 · §15) ═════════════════
def test_valid_inputs_pass():
    inputs = _validate()
    assert inputs.pr_number == "903"
    assert inputs.expected_head == HEAD
    assert inputs.expected_tree == TREE
    assert inputs.event_name == "workflow_dispatch"


# ══ 고정 상수 불일치 ═══════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("pr_number", "904", wi.INPUT_PR_NUMBER_MISMATCH),
        ("pr_number", " 903", wi.INPUT_PR_NUMBER_MISMATCH),
        ("repository", "attacker/repo", wi.INPUT_REPOSITORY_MISMATCH),
        ("ref", "refs/heads/feature", wi.INPUT_REF_MISMATCH),
        ("ref", "refs/pull/903/merge", wi.INPUT_REF_MISMATCH),
        ("event_name", "pull_request", wi.INPUT_EVENT_MISMATCH),
        ("event_name", "workflow_run", wi.INPUT_EVENT_MISMATCH),
    ],
)
def test_constant_mismatch_is_rejected(field, value, code):
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(**{field: value})
    assert caught.value.code == code


# ══ OID 형식 ═══════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "value",
    [
        "",
        "61ba1bf4",
        HEAD.upper(),
        HEAD + "0",
        " " + HEAD,
        HEAD + " ",
        HEAD + "\n",
        "\n" + HEAD,
        f"{HEAD}\nrefs/heads/main",
        "61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd0g",
        "61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd0а",
    ],
)
def test_malformed_head_is_rejected(value):
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(expected_head=value)
    assert caught.value.code in {wi.INPUT_HEAD_MALFORMED, wi.INPUT_MISSING}


def test_newline_cannot_smuggle_a_second_value():
    """\\A…\\Z 를 쓰므로 줄바꿈이 섞인 값은 통과하지 못한다.

    ^…$ 였다면 여러 줄 중 한 줄만 맞아도 통과했을 것이다.
    """
    with pytest.raises(wi.WorkflowInputError):
        _validate(expected_head=f"{HEAD}\n{HEAD}")


# ══ 잠금과의 완전일치 ══════════════════════════════════════════════════
def test_head_not_matching_lock_is_rejected():
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(locked_head="a" * 40)
    assert caught.value.code == wi.INPUT_HEAD_NOT_LOCKED


def test_tree_not_matching_lock_is_rejected():
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(locked_tree="b" * 40)
    assert caught.value.code == wi.INPUT_TREE_NOT_LOCKED


def test_malformed_lock_value_is_rejected():
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(locked_head="not-an-oid")
    assert caught.value.code == wi.INPUT_HEAD_NOT_LOCKED


# ══ run_id ═════════════════════════════════════════════════════════════
@pytest.mark.parametrize("value", ["", "abc", "-1", "1e5", "1 2", "9" * 21, "12\n34"])
def test_malformed_run_id_is_rejected(value):
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(run_id=value)
    assert caught.value.code in {wi.INPUT_RUN_ID_MALFORMED, wi.INPUT_MISSING}


def test_run_id_upper_length_bound_is_enforced():
    assert _validate(run_id="9" * 20).run_id == "9" * 20
    with pytest.raises(wi.WorkflowInputError):
        _validate(run_id="9" * 21)


# ══ 누락·비문자열 ══════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "field",
    ["pr_number", "expected_head", "expected_tree", "run_id", "repository", "ref", "event_name"],
)
def test_missing_value_is_rejected(field):
    with pytest.raises(wi.WorkflowInputError):
        _validate(**{field: None})


@pytest.mark.parametrize("value", [903, 903.0, True, [], {}])
def test_non_string_value_is_rejected(value):
    with pytest.raises(wi.WorkflowInputError) as caught:
        _validate(pr_number=value)
    assert caught.value.code == wi.INPUT_MISSING


def test_module_never_rewrites_a_value():
    """★값을 고쳐서 통과시키지 않는다. 받아들이거나 닫는다."""
    source = __import__("inspect").getsource(wi)
    for rewriting in (".replace(", ".strip()", ".lstrip(", ".rstrip(", "re.sub("):
        assert rewriting not in source, rewriting
