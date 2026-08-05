"""§8 M-4 — workflow 입력·출력의 script injection 차단.

workflow_dispatch 입력을 셸 run 본문에 직접 넣으면, 검증기를 실행하는 사람이 그
값에 명령을 심을 수 있다. M-2 로 막으려던 것이 입구에서 뚫린다.

계약
  · 모든 입력은 env 로 전달된 뒤 이 모듈에서 strict 검증한다.
  · 검증은 ★허용 형태만 통과★ 시킨다. 위험 문자를 지우는 방식이 아니다.
    지우는 방식은 새 우회가 나올 때마다 뚫린다.
  · payload 는 실행되지 않고 INPUT_* 오류 코드로 끝난다.

이 모듈은 값을 고치지 않는다. 받아들이거나 닫는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ── 오류 코드 ──────────────────────────────────────────────────────────
INPUT_PR_NUMBER_MISMATCH = "INPUT_PR_NUMBER_MISMATCH"
INPUT_HEAD_MALFORMED = "INPUT_HEAD_MALFORMED"
INPUT_TREE_MALFORMED = "INPUT_TREE_MALFORMED"
INPUT_HEAD_NOT_LOCKED = "INPUT_HEAD_NOT_LOCKED"
INPUT_TREE_NOT_LOCKED = "INPUT_TREE_NOT_LOCKED"
INPUT_RUN_ID_MALFORMED = "INPUT_RUN_ID_MALFORMED"
INPUT_REPOSITORY_MISMATCH = "INPUT_REPOSITORY_MISMATCH"
INPUT_REF_MISMATCH = "INPUT_REF_MISMATCH"
INPUT_EVENT_MISMATCH = "INPUT_EVENT_MISMATCH"
INPUT_MISSING = "INPUT_MISSING"

# ── 고정 상수 (부르는 쪽이 고를 수 없다) ───────────────────────────────
EXPECTED_PR_NUMBER = "903"
EXPECTED_REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
EXPECTED_REF = "refs/heads/main"
EXPECTED_EVENT = "workflow_dispatch"

# ★허용 형태만 통과. 40자 소문자 hex 하나. 앞뒤 공백도 허용하지 않는다.
_OID_RE = re.compile(r"\A[0-9a-f]{40}\Z")
# run_id 는 ASCII 십진수. 길이 상한을 둔다.
_RUN_ID_RE = re.compile(r"\A[0-9]{1,20}\Z")


class WorkflowInputError(Exception):
    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"{code}: {field}")
        self.code = code
        self.field = field


@dataclass(frozen=True)
class DispatchInputs:
    pr_number: str
    expected_head: str
    expected_tree: str
    run_id: str
    repository: str
    ref: str
    event_name: str


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise WorkflowInputError(INPUT_MISSING, field)
    return value


def _exact(value: object, expected: str, field: str, code: str) -> str:
    text = _require_text(value, field)
    if text != expected:
        raise WorkflowInputError(code, field)
    return text


def _oid(value: object, field: str, code: str) -> str:
    text = _require_text(value, field)
    # \A…\Z 이므로 줄바꿈이 섞인 값은 통과하지 못한다
    if _OID_RE.match(text) is None:
        raise WorkflowInputError(code, field)
    return text


def validate_dispatch_inputs(
    *,
    pr_number: object,
    expected_head: object,
    expected_tree: object,
    run_id: object,
    repository: object,
    ref: object,
    event_name: object,
    locked_head: str,
    locked_tree: str,
) -> DispatchInputs:
    """workflow_dispatch 입력 전부를 strict 검증한다.

    locked_head·locked_tree 는 보호된 잠금에서 온 값이다. 입력은 그것과 완전히
    같아야 한다 — 입력은 권위값이 아니라 대조할 주장값이다.
    """
    inputs = DispatchInputs(
        pr_number=_exact(pr_number, EXPECTED_PR_NUMBER, "pr_number", INPUT_PR_NUMBER_MISMATCH),
        expected_head=_oid(expected_head, "expected_head", INPUT_HEAD_MALFORMED),
        expected_tree=_oid(expected_tree, "expected_tree", INPUT_TREE_MALFORMED),
        run_id=_run_id(run_id),
        repository=_exact(
            repository, EXPECTED_REPOSITORY, "repository", INPUT_REPOSITORY_MISMATCH
        ),
        ref=_exact(ref, EXPECTED_REF, "ref", INPUT_REF_MISMATCH),
        event_name=_exact(event_name, EXPECTED_EVENT, "event_name", INPUT_EVENT_MISMATCH),
    )
    if _OID_RE.match(locked_head or "") is None or inputs.expected_head != locked_head:
        raise WorkflowInputError(INPUT_HEAD_NOT_LOCKED, "expected_head")
    if _OID_RE.match(locked_tree or "") is None or inputs.expected_tree != locked_tree:
        raise WorkflowInputError(INPUT_TREE_NOT_LOCKED, "expected_tree")
    return inputs


def _run_id(value: object) -> str:
    text = _require_text(value, "run_id")
    if _RUN_ID_RE.match(text) is None:
        raise WorkflowInputError(INPUT_RUN_ID_MALFORMED, "run_id")
    return text


__all__ = [
    "EXPECTED_EVENT",
    "EXPECTED_PR_NUMBER",
    "EXPECTED_REF",
    "EXPECTED_REPOSITORY",
    "INPUT_EVENT_MISMATCH",
    "INPUT_HEAD_MALFORMED",
    "INPUT_HEAD_NOT_LOCKED",
    "INPUT_MISSING",
    "INPUT_PR_NUMBER_MISMATCH",
    "INPUT_REF_MISMATCH",
    "INPUT_REPOSITORY_MISMATCH",
    "INPUT_RUN_ID_MALFORMED",
    "INPUT_TREE_MALFORMED",
    "INPUT_TREE_NOT_LOCKED",
    "DispatchInputs",
    "WorkflowInputError",
    "validate_dispatch_inputs",
]
