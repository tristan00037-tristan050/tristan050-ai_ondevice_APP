"""F-01 — 읽어 온 사실의 ★의미★ 를 검증한다.

감사 R6 판정(PRIMARY_BLOCK=R6_3_PREFLIGHT_FALSE_PASS)의 뿌리는 이것이었다.

    사전점검이 2xx 인지만 보고, 응답 ★내용★ 은 보지 않았다.

그래서 다음 여섯이 전부 통과했다.

    approval commit 응답 {}                → OK
    approval compare status=diverged       → OK
    candidate commit tree = 9…9            → OK
    approver 응답 login=attacker           → OK
    main branch protection 응답 {}         → OK
    workflow run 응답 {}                   → OK

신뢰 관문의 핵심은 요청 수나 시험 수가 아니라 ★잘못된 사실을 반드시 거부하는가★ 다.

이 모듈은 endpoint 별로 "이 응답이 무엇을 뜻해야 하는가" 를 한 곳에 모은다.
읽기(transport)와 판정(여기)을 분리해야, 읽었는데 안 본 사실이 생기지 않는다.

★규칙
  · 각 검사는 안정된 오류 코드 하나를 낸다. 예외 문자열을 계약으로 쓰지 않는다.
  · 모르는 것·빠진 것·형식이 틀린 것은 전부 거부다(fail-closed).
  · payload 원문을 오류에 담지 않는다. 코드만 낸다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ── 오류 코드 (F-01) ───────────────────────────────────────────────────
PREFLIGHT_APPROVAL_REPO_MISMATCH = "PREFLIGHT_APPROVAL_REPO_MISMATCH"
PREFLIGHT_APPROVAL_REF_MISMATCH = "PREFLIGHT_APPROVAL_REF_MISMATCH"
PREFLIGHT_APPROVAL_COMMIT_INVALID = "PREFLIGHT_APPROVAL_COMMIT_INVALID"
PREFLIGHT_APPROVAL_NOT_ANCESTOR = "PREFLIGHT_APPROVAL_NOT_ANCESTOR"
PREFLIGHT_CONTENTS_PATH_MISMATCH = "PREFLIGHT_CONTENTS_PATH_MISMATCH"
PREFLIGHT_APPROVER_MISMATCH = "PREFLIGHT_APPROVER_MISMATCH"
PREFLIGHT_CANDIDATE_HEAD_MISMATCH = "PREFLIGHT_CANDIDATE_HEAD_MISMATCH"
PREFLIGHT_CANDIDATE_TREE_MISMATCH = "PREFLIGHT_CANDIDATE_TREE_MISMATCH"
PREFLIGHT_CANDIDATE_REPO_MISMATCH = "PREFLIGHT_CANDIDATE_REPO_MISMATCH"
PREFLIGHT_BRANCH_NOT_PROTECTED = "PREFLIGHT_BRANCH_NOT_PROTECTED"
PREFLIGHT_BRANCH_HEAD_MISMATCH = "PREFLIGHT_BRANCH_HEAD_MISMATCH"
PREFLIGHT_RUN_FACT_INVALID = "PREFLIGHT_RUN_FACT_INVALID"
PREFLIGHT_ENVIRONMENT_MISMATCH = "PREFLIGHT_ENVIRONMENT_MISMATCH"
PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED = "PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED"

# compare API 에서 head 가 base 의 조상임을 뜻하는 상태. 그 밖은 전부 거부다.
ANCESTOR_STATES = frozenset({"behind", "identical"})

APPROVED_RUN_EVENT = "workflow_dispatch"
APPROVED_BRANCH_NAME = "main"

_OID_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_UTC_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")


class FactRejected(Exception):
    """사실이 기대와 다르다. 코드만 갖고 다닌다 — payload 를 담지 않는다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _obj(payload: object, code: str) -> dict:
    if not isinstance(payload, dict) or not payload:
        # ★빈 객체 {} 도 거부다. 감사가 든 부정 사실 넷이 정확히 이 모양이었다.
        raise FactRejected(code)
    return payload


def _text(container: dict, key: str, code: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value:
        raise FactRejected(code)
    return value


def _nested_text(container: dict, outer: str, inner: str, code: str) -> str:
    nested = container.get(outer)
    if not isinstance(nested, dict):
        raise FactRejected(code)
    return _text(nested, inner, code)


def _oid(value: str, code: str) -> str:
    if _OID_RE.match(value) is None:
        raise FactRejected(code)
    return value


# ══ 승인 저장소 ════════════════════════════════════════════════════════
def verify_approval_repository(payload: object, *, expected_repository: str) -> None:
    repo = _obj(payload, PREFLIGHT_APPROVAL_REPO_MISMATCH)
    if _text(repo, "full_name", PREFLIGHT_APPROVAL_REPO_MISMATCH) != expected_repository:
        raise FactRejected(PREFLIGHT_APPROVAL_REPO_MISMATCH)


def verify_approval_ref(payload: object, *, expected_ref: str) -> str:
    """보호 ref 응답을 검증하고 ★그 ref 가 가리키는 커밋★ 을 돌려준다."""
    ref = _obj(payload, PREFLIGHT_APPROVAL_REF_MISMATCH)
    if _text(ref, "ref", PREFLIGHT_APPROVAL_REF_MISMATCH) != expected_ref:
        raise FactRejected(PREFLIGHT_APPROVAL_REF_MISMATCH)
    return _oid(
        _nested_text(ref, "object", "sha", PREFLIGHT_APPROVAL_REF_MISMATCH),
        PREFLIGHT_APPROVAL_REF_MISMATCH,
    )


def verify_approval_commit(payload: object, *, expected_commit: str) -> str:
    """승인 커밋 응답을 검증하고 committer 시각을 돌려준다.

    감사 부정 사실 ①: 응답이 `{}` 여도 통과했다. 이제 sha·committer 시각을 모두
    요구하므로 빈 객체는 첫 줄에서 닫힌다.
    """
    commit = _obj(payload, PREFLIGHT_APPROVAL_COMMIT_INVALID)
    if _text(commit, "sha", PREFLIGHT_APPROVAL_COMMIT_INVALID) != expected_commit:
        raise FactRejected(PREFLIGHT_APPROVAL_COMMIT_INVALID)
    body = commit.get("commit")
    if not isinstance(body, dict):
        raise FactRejected(PREFLIGHT_APPROVAL_COMMIT_INVALID)
    date = _nested_text(body, "committer", "date", PREFLIGHT_APPROVAL_COMMIT_INVALID)
    if _UTC_RE.match(date) is None:
        raise FactRejected(PREFLIGHT_APPROVAL_COMMIT_INVALID)
    return date


def verify_ancestry(payload: object) -> None:
    """compare 응답의 status 가 조상 관계인지 본다.

    감사 부정 사실 ②: `status=diverged` 여도 통과했다. 형식만 보고 의미를 안 봤다.
    """
    compare = _obj(payload, PREFLIGHT_APPROVAL_NOT_ANCESTOR)
    status = _text(compare, "status", PREFLIGHT_APPROVAL_NOT_ANCESTOR)
    if status not in ANCESTOR_STATES:
        raise FactRejected(PREFLIGHT_APPROVAL_NOT_ANCESTOR)


def verify_contents_path(payload: object, *, expected_path: str) -> None:
    """contents 응답이 ★요청한 그 경로★ 를 돌려주었는지 본다."""
    contents = _obj(payload, PREFLIGHT_CONTENTS_PATH_MISMATCH)
    if _text(contents, "path", PREFLIGHT_CONTENTS_PATH_MISMATCH) != expected_path:
        raise FactRejected(PREFLIGHT_CONTENTS_PATH_MISMATCH)


def verify_approver(payload: object, *, expected_login: str, expected_id: int) -> None:
    """승인자 응답의 login 과 id 를 ★승인 문서★ 값과 대조한다.

    감사 부정 사실 ④: `login=attacker` 여도 통과했다. 응답을 읽고 버렸기 때문이다.
    """
    user = _obj(payload, PREFLIGHT_APPROVER_MISMATCH)
    if _text(user, "login", PREFLIGHT_APPROVER_MISMATCH) != expected_login:
        raise FactRejected(PREFLIGHT_APPROVER_MISMATCH)
    account_id = user.get("id")
    if not isinstance(account_id, int) or isinstance(account_id, bool):
        raise FactRejected(PREFLIGHT_APPROVER_MISMATCH)
    if account_id != expected_id:
        raise FactRejected(PREFLIGHT_APPROVER_MISMATCH)


# ══ 후보 저장소 ════════════════════════════════════════════════════════
def verify_candidate_pull(payload: object, *, expected_head: str) -> str:
    pull = _obj(payload, PREFLIGHT_CANDIDATE_HEAD_MISMATCH)
    sha = _nested_text(pull, "head", "sha", PREFLIGHT_CANDIDATE_HEAD_MISMATCH)
    if _oid(sha, PREFLIGHT_CANDIDATE_HEAD_MISMATCH) != expected_head:
        raise FactRejected(PREFLIGHT_CANDIDATE_HEAD_MISMATCH)
    return sha


def verify_candidate_commit(
    payload: object, *, expected_commit: str, expected_tree: str
) -> None:
    """후보 커밋의 sha 와 ★tree★ 를 잠긴 좌표와 대조한다.

    감사 부정 사실 ③: tree 가 `9…9` 여도 통과했다. 잠긴 tree 는 자리표 검사에만
    쓰이고 실제 대조에는 한 번도 안 쓰였다.
    """
    commit = _obj(payload, PREFLIGHT_CANDIDATE_TREE_MISMATCH)
    sha = _text(commit, "sha", PREFLIGHT_CANDIDATE_TREE_MISMATCH)
    if _oid(sha, PREFLIGHT_CANDIDATE_TREE_MISMATCH) != expected_commit:
        raise FactRejected(PREFLIGHT_CANDIDATE_HEAD_MISMATCH)
    tree = _nested_text(commit, "tree", "sha", PREFLIGHT_CANDIDATE_TREE_MISMATCH)
    if _oid(tree, PREFLIGHT_CANDIDATE_TREE_MISMATCH) != expected_tree:
        raise FactRejected(PREFLIGHT_CANDIDATE_TREE_MISMATCH)


def verify_candidate_repository(payload: object, *, expected_repository: str) -> None:
    repo = _obj(payload, PREFLIGHT_CANDIDATE_REPO_MISMATCH)
    if _text(repo, "full_name", PREFLIGHT_CANDIDATE_REPO_MISMATCH) != expected_repository:
        raise FactRejected(PREFLIGHT_CANDIDATE_REPO_MISMATCH)


def verify_protected_branch(payload: object, *, expected_head: str) -> None:
    """main 이 실제로 보호돼 있고, 그 head 가 지금 실행 커밋과 같은지 본다.

    감사 부정 사실 ⑤: 응답이 `{}` 여도 통과했다. 보호 여부를 아예 안 봤다.
    """
    branch = _obj(payload, PREFLIGHT_BRANCH_NOT_PROTECTED)
    if branch.get("protected") is not True:
        raise FactRejected(PREFLIGHT_BRANCH_NOT_PROTECTED)
    sha = _nested_text(branch, "commit", "sha", PREFLIGHT_BRANCH_NOT_PROTECTED)
    if _oid(sha, PREFLIGHT_BRANCH_NOT_PROTECTED) != expected_head:
        # main 이 실행 시작 뒤 전진했거나 다른 커밋을 가리킨다 — 닫는다
        raise FactRejected(PREFLIGHT_BRANCH_HEAD_MISMATCH)


def verify_run(
    payload: object, *, expected_run_id: int, expected_repository: str
) -> tuple[str, str]:
    """workflow run 응답을 검증하고 (head_sha, run_started_at) 을 돌려준다.

    감사 부정 사실 ⑥: 응답이 `{}` 여도 통과했다. dict 인지만 봤기 때문이다.
    """
    run = _obj(payload, PREFLIGHT_RUN_FACT_INVALID)
    run_id = run.get("id")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id != expected_run_id:
        raise FactRejected(PREFLIGHT_RUN_FACT_INVALID)
    if _text(run, "event", PREFLIGHT_RUN_FACT_INVALID) != APPROVED_RUN_EVENT:
        raise FactRejected(PREFLIGHT_RUN_FACT_INVALID)
    if _text(run, "head_branch", PREFLIGHT_RUN_FACT_INVALID) != APPROVED_BRANCH_NAME:
        raise FactRejected(PREFLIGHT_RUN_FACT_INVALID)
    head_sha = _oid(
        _text(run, "head_sha", PREFLIGHT_RUN_FACT_INVALID), PREFLIGHT_RUN_FACT_INVALID
    )
    if (
        _nested_text(run, "repository", "full_name", PREFLIGHT_RUN_FACT_INVALID)
        != expected_repository
    ):
        raise FactRejected(PREFLIGHT_RUN_FACT_INVALID)
    started = _text(run, "run_started_at", PREFLIGHT_RUN_FACT_INVALID)
    if _UTC_RE.match(started) is None:
        raise FactRejected(PREFLIGHT_RUN_FACT_INVALID)
    return head_sha, started


def verify_environment(payload: object, *, expected_name: str) -> None:
    environment = _obj(payload, PREFLIGHT_ENVIRONMENT_MISMATCH)
    if _text(environment, "name", PREFLIGHT_ENVIRONMENT_MISMATCH) != expected_name:
        raise FactRejected(PREFLIGHT_ENVIRONMENT_MISMATCH)
    policy = environment.get("deployment_branch_policy")
    if not isinstance(policy, dict):
        raise FactRejected(PREFLIGHT_ENVIRONMENT_MISMATCH)
    if policy.get("custom_branch_policies") is not True:
        raise FactRejected(PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED)


def verify_branch_policies(payload: object, *, expected_branch: str) -> None:
    policies = _obj(payload, PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED)
    branches = policies.get("branch_policies")
    if not isinstance(branches, list):
        raise FactRejected(PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED)
    names = [entry.get("name") for entry in branches if isinstance(entry, dict)]
    if names != [expected_branch]:
        raise FactRejected(PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED)


@dataclass(frozen=True)
class FactRule:
    """endpoint 하나에 붙는 검사. 읽고 안 보는 사실이 생기지 않게 목록으로 강제한다."""

    label: str
    code: str


# ★읽은 사실에는 반드시 검사가 하나씩 붙는다. 이 목록이 그 계약이다.
REQUIRED_FACT_RULES = (
    FactRule("approval_repository", PREFLIGHT_APPROVAL_REPO_MISMATCH),
    FactRule("approval_ref", PREFLIGHT_APPROVAL_REF_MISMATCH),
    FactRule("approval_commit", PREFLIGHT_APPROVAL_COMMIT_INVALID),
    FactRule("approval_document", PREFLIGHT_CONTENTS_PATH_MISMATCH),
    FactRule("approval_signature", PREFLIGHT_CONTENTS_PATH_MISMATCH),
    FactRule("approval_allowed_signers", PREFLIGHT_CONTENTS_PATH_MISMATCH),
    FactRule("approval_compare", PREFLIGHT_APPROVAL_NOT_ANCESTOR),
    FactRule("approver", PREFLIGHT_APPROVER_MISMATCH),
    FactRule("candidate_pull", PREFLIGHT_CANDIDATE_HEAD_MISMATCH),
    FactRule("candidate_commit", PREFLIGHT_CANDIDATE_TREE_MISMATCH),
    FactRule("candidate_repository", PREFLIGHT_CANDIDATE_REPO_MISMATCH),
    FactRule("candidate_branch", PREFLIGHT_BRANCH_NOT_PROTECTED),
    FactRule("candidate_environment", PREFLIGHT_ENVIRONMENT_MISMATCH),
    FactRule("candidate_branch_policies", PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED),
    FactRule("workflow_run", PREFLIGHT_RUN_FACT_INVALID),
)


__all__ = [
    "ANCESTOR_STATES",
    "APPROVED_BRANCH_NAME",
    "APPROVED_RUN_EVENT",
    "PREFLIGHT_APPROVAL_COMMIT_INVALID",
    "PREFLIGHT_APPROVAL_NOT_ANCESTOR",
    "PREFLIGHT_APPROVAL_REF_MISMATCH",
    "PREFLIGHT_APPROVAL_REPO_MISMATCH",
    "PREFLIGHT_APPROVER_MISMATCH",
    "PREFLIGHT_BRANCH_HEAD_MISMATCH",
    "PREFLIGHT_BRANCH_NOT_PROTECTED",
    "PREFLIGHT_BRANCH_POLICY_MODE_UNAPPROVED",
    "PREFLIGHT_CANDIDATE_HEAD_MISMATCH",
    "PREFLIGHT_CANDIDATE_REPO_MISMATCH",
    "PREFLIGHT_CANDIDATE_TREE_MISMATCH",
    "PREFLIGHT_CONTENTS_PATH_MISMATCH",
    "PREFLIGHT_ENVIRONMENT_MISMATCH",
    "PREFLIGHT_RUN_FACT_INVALID",
    "FactRejected",
    "FactRule",
    "REQUIRED_FACT_RULES",
    "verify_ancestry",
    "verify_approval_commit",
    "verify_approval_ref",
    "verify_approval_repository",
    "verify_approver",
    "verify_branch_policies",
    "verify_candidate_commit",
    "verify_candidate_pull",
    "verify_candidate_repository",
    "verify_contents_path",
    "verify_environment",
    "verify_protected_branch",
    "verify_run",
]
