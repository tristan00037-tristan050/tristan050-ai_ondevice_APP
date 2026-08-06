"""F-01 — 감사가 재현한 여섯 부정 사실을 ★반드시 거부하는가★.

R6 독립 감사 판정
    PRIMARY_BLOCK=R6_3_PREFLIGHT_FALSE_PASS

감사는 다음 여섯을 각각 먹였고, 여섯 다 `ok=True, OK` 로 통과했다.

    approval commit 응답 {}                → OK
    approval compare status=diverged       → OK
    candidate commit tree = 9…9            → OK
    approver 응답 login=attacker           → OK
    main branch protection 응답 {}         → OK
    workflow run 응답 {}                   → OK

지시서 §4-3: **여섯 중 하나라도 OK 가 나오면 실패다.**

이 파일이 그 여섯을 행렬로 고정한다. 여기에 더해, 각 사실이 ★어떤 코드로★
거부되는지까지 못박는다 — nonzero 였다는 이유만으로 통과시키지 않는다(§11-2).
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from urllib.parse import unquote

import pytest
from ac25 import anchors, lock_verifier
from ac25 import preflight_facts as pf
from ac25 import remote_facts as rf
from ac25 import token_preflight as tp
from ac25 import workflow_identity

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

DOCUMENT_BYTES = (FIXTURES / "approval_document.md").read_bytes()
DOCUMENT_SHA256 = hashlib.sha256(DOCUMENT_BYTES).hexdigest()

LOCK = lock_verifier.load_candidate_lock(
    (REPO_ROOT / anchors.CANDIDATE_LOCK_PATH).read_bytes()
)
LOCKED_HEAD = LOCK.approved_head_commit
LOCKED_TREE = LOCK.approved_head_tree

APPROVAL_MAIN = "a" * 40        # 승인 저장소 main
CANDIDATE_MAIN = "c" * 40       # 후보 저장소 main = 이 run 의 head
RUN_ID = 31058574141
APPROVER = "tristan00037-tristan050"
APPROVER_ID = 238947383


@pytest.fixture(autouse=True)
def _pin_document_digest(monkeypatch):
    monkeypatch.setattr(anchors, "APPROVAL_DOCUMENT_SHA256", DOCUMENT_SHA256)
    monkeypatch.setattr(tp.anchors, "APPROVAL_DOCUMENT_SHA256", DOCUMENT_SHA256)


def _contents(data: bytes, path: str) -> dict:
    return {
        "encoding": "base64",
        "content": base64.b64encode(data).decode("ascii"),
        "path": path,
    }


def _endpoints():
    return tp.build_endpoints(
        pr_number=anchors.CANDIDATE_PR_NUMBER,
        candidate_head_sha=LOCKED_HEAD,
        approver_login=APPROVER,
    )


def _truthful_table() -> dict[str, object]:
    """★사실이 전부 참인 응답표. 여기서 한 칸만 거짓으로 바꿔 공격한다."""
    e = _endpoints()
    return {
        e.approval_repo(): {"full_name": anchors.APPROVAL_REPOSITORY},
        e.approval_ref(): {"ref": anchors.APPROVAL_PROTECTED_REF,
                           "object": {"sha": APPROVAL_MAIN}},
        e.approval_commit(): {
            "sha": anchors.APPROVAL_COMMIT_SHA,
            "commit": {"committer": {"date": "2026-08-05T04:48:43Z"}},
        },
        e.approval_contents(anchors.APPROVAL_DOCUMENT_PATH):
            _contents(DOCUMENT_BYTES, anchors.APPROVAL_DOCUMENT_PATH),
        e.approval_contents(anchors.APPROVAL_SIGNATURE_PATH):
            _contents(b"sig", anchors.APPROVAL_SIGNATURE_PATH),
        e.approval_contents(anchors.APPROVAL_ALLOWED_SIGNERS_PATH):
            _contents(b"signers", anchors.APPROVAL_ALLOWED_SIGNERS_PATH),
        e.approval_compare(APPROVAL_MAIN): {"status": "behind"},
        e.approver(): {"login": APPROVER, "id": APPROVER_ID},
        e.candidate_pull(): {"head": {"sha": LOCKED_HEAD}, "base": {"sha": "2" * 40}},
        e.candidate_commit(LOCKED_HEAD): {"sha": LOCKED_HEAD, "tree": {"sha": LOCKED_TREE}},
        e.candidate_repo(): {"full_name": anchors.CANDIDATE_REPOSITORY},
        e.candidate_branch("main"): {"protected": True,
                                     "commit": {"sha": CANDIDATE_MAIN}},
        e.candidate_environment(): {
            "name": workflow_identity.EXPECTED_ENVIRONMENT,
            "deployment_branch_policy": {"custom_branch_policies": True},
        },
        e.candidate_environment_policies(): {"branch_policies": [{"name": "main"}]},
        f"repos/{anchors.CANDIDATE_REPOSITORY}/actions/runs/{RUN_ID}": {
            "id": RUN_ID,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": CANDIDATE_MAIN,
            "repository": {"full_name": anchors.CANDIDATE_REPOSITORY},
            "run_started_at": "2026-08-06T00:00:00Z",
        },
    }


def _run(table: dict[str, object]) -> tp.PreflightResult:
    def send(path: str) -> rf.TransportResult:
        if path in table:
            return rf.TransportResult(status=200, payload=table[path])
        return rf.TransportResult(status=404)

    router = rf.TransportRouter(approval=send, candidate=send, run=send)
    return tp.run_preflight(
        router=router, run_id=RUN_ID,
        locked_candidate_head=LOCKED_HEAD, locked_candidate_tree=LOCKED_TREE,
    )


def _with(path: str, payload: object) -> dict[str, object]:
    table = _truthful_table()
    table[path] = payload
    return table


# ══ 양성 — 참인 사실은 실제로 통과해야 한다 ═══════════════════════════
def test_truthful_facts_pass():
    """막기만 하는 검사기는 합격이 아니다(§3-7). 참이면 통과해야 한다."""
    result = _run(_truthful_table())
    assert result.ok is True, result.error_code
    assert result.error_code == "OK"
    assert result.reached_state == tp.State.PREFLIGHT_VERDICT.value


# ══ 감사가 든 여섯 부정 사실 ═══════════════════════════════════════════
def _six_attacks():
    e = _endpoints()
    return [
        ("approval_commit_empty", e.approval_commit(), {},
         pf.PREFLIGHT_APPROVAL_COMMIT_INVALID),
        ("compare_diverged", e.approval_compare(APPROVAL_MAIN), {"status": "diverged"},
         pf.PREFLIGHT_APPROVAL_NOT_ANCESTOR),
        ("candidate_tree_forged", e.candidate_commit(LOCKED_HEAD),
         {"sha": LOCKED_HEAD, "tree": {"sha": "9" * 40}},
         pf.PREFLIGHT_CANDIDATE_TREE_MISMATCH),
        ("approver_attacker", e.approver(), {"login": "attacker", "id": 1},
         pf.PREFLIGHT_APPROVER_MISMATCH),
        ("branch_protection_empty", e.candidate_branch("main"), {},
         pf.PREFLIGHT_BRANCH_NOT_PROTECTED),
        ("workflow_run_empty",
         f"repos/{anchors.CANDIDATE_REPOSITORY}/actions/runs/{RUN_ID}", {},
         pf.PREFLIGHT_RUN_FACT_INVALID),
    ]


@pytest.mark.parametrize(
    ("label", "path", "payload", "expected_code"),
    _six_attacks(),
    ids=[item[0] for item in _six_attacks()],
)
def test_each_audited_false_fact_is_rejected(label, path, payload, expected_code):
    """여섯 각각이 ★기대 코드까지★ 일치해 거부되는지 본다."""
    result = _run(_with(path, payload))
    assert result.ok is False, f"{label} 이 통과했다 — 거짓 통과다"
    assert result.error_code == expected_code, (label, result.error_code)


def test_no_audited_false_fact_survives():
    """행렬 전체를 한 번에 — 하나라도 OK 면 실패다(§4-3)."""
    survivors = [
        label for label, path, payload, _code in _six_attacks()
        if _run(_with(path, payload)).ok
    ]
    assert survivors == [], survivors


# ══ 같은 자리의 다른 거짓들 — 행렬을 넓힌다 ════════════════════════════
@pytest.mark.parametrize("status", ["diverged", "ahead", "", "BEHIND", "unknown"])
def test_only_behind_or_identical_counts_as_ancestor(status):
    e = _endpoints()
    result = _run(_with(e.approval_compare(APPROVAL_MAIN), {"status": status}))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_APPROVAL_NOT_ANCESTOR


@pytest.mark.parametrize("status", ["behind", "identical"])
def test_ancestor_states_pass(status):
    e = _endpoints()
    result = _run(_with(e.approval_compare(APPROVAL_MAIN), {"status": status}))
    assert result.ok is True, result.error_code


def test_approver_id_mismatch_is_rejected_even_when_login_matches():
    """login 만 맞고 id 가 다른 계정은 거부한다 — 이름은 바뀔 수 있다."""
    e = _endpoints()
    result = _run(_with(e.approver(), {"login": APPROVER, "id": 999}))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_APPROVER_MISMATCH


def test_unprotected_main_is_rejected():
    e = _endpoints()
    result = _run(_with(
        e.candidate_branch("main"),
        {"protected": False, "commit": {"sha": CANDIDATE_MAIN}},
    ))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_BRANCH_NOT_PROTECTED


def test_main_moved_after_run_started_is_rejected():
    """main 이 실행 뒤 전진하면 닫는다 — 다른 main 을 검증한 셈이 된다."""
    e = _endpoints()
    result = _run(_with(
        e.candidate_branch("main"),
        {"protected": True, "commit": {"sha": "d" * 40}},
    ))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_BRANCH_HEAD_MISMATCH


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 999),
        ("event", "push"),
        ("event", "pull_request_target"),
        ("head_branch", "attacker-branch"),
        ("run_started_at", "not-a-time"),
        ("head_sha", "zz"),
    ],
)
def test_run_fact_fields_are_each_enforced(field, value):
    table = _truthful_table()
    key = f"repos/{anchors.CANDIDATE_REPOSITORY}/actions/runs/{RUN_ID}"
    payload = dict(table[key])
    payload[field] = value
    result = _run(_with(key, payload))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_RUN_FACT_INVALID


def test_run_from_another_repository_is_rejected():
    table = _truthful_table()
    key = f"repos/{anchors.CANDIDATE_REPOSITORY}/actions/runs/{RUN_ID}"
    payload = dict(table[key])
    payload["repository"] = {"full_name": "attacker/repo"}
    result = _run(_with(key, payload))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_RUN_FACT_INVALID


def test_approval_commit_of_a_different_commit_is_rejected():
    e = _endpoints()
    result = _run(_with(e.approval_commit(), {
        "sha": "f" * 40,
        "commit": {"committer": {"date": "2026-08-05T04:48:43Z"}},
    }))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_APPROVAL_COMMIT_INVALID


def test_approval_repository_substitution_is_rejected():
    e = _endpoints()
    result = _run(_with(e.approval_repo(), {"full_name": "attacker/butler-ct-shared"}))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_APPROVAL_REPO_MISMATCH


def test_protected_ref_substitution_is_rejected():
    e = _endpoints()
    result = _run(_with(e.approval_ref(), {
        "ref": "refs/heads/attacker", "object": {"sha": APPROVAL_MAIN},
    }))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_APPROVAL_REF_MISMATCH


def test_contents_response_for_another_path_is_rejected():
    """요청한 경로와 다른 파일을 돌려주면 거부한다."""
    e = _endpoints()
    result = _run(_with(
        e.approval_contents(anchors.APPROVAL_SIGNATURE_PATH),
        _contents(b"sig", "docs/decisions/다른파일.md"),
    ))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_CONTENTS_PATH_MISMATCH


def test_candidate_repository_substitution_is_rejected():
    e = _endpoints()
    result = _run(_with(e.candidate_repo(), {"full_name": "attacker/app"}))
    assert result.ok is False
    assert result.error_code == pf.PREFLIGHT_CANDIDATE_REPO_MISMATCH


# ══ 계약 — 읽은 사실에는 반드시 검사가 붙는다 ══════════════════════════
def test_every_read_fact_has_a_rule():
    """★읽었는데 안 보는 사실★ 이 생기지 않게 목록으로 고정한다."""
    labels = {rule.label for rule in pf.REQUIRED_FACT_RULES}
    assert len(labels) == len(pf.REQUIRED_FACT_RULES), "이름표가 중복이다"

    # 정상 실행이 읽은 사실이 그 목록과 정확히 같아야 한다
    machine_facts: dict = {}

    original = tp._Machine.s6_verdict

    def spy(self):
        machine_facts.update(self.facts)
        return original(self)

    tp._Machine.s6_verdict = spy
    try:
        result = _run(_truthful_table())
    finally:
        tp._Machine.s6_verdict = original
    assert result.ok, result.error_code
    assert set(machine_facts) == labels, set(machine_facts) ^ labels


def test_every_fact_rule_code_is_a_stable_constant():
    for rule in pf.REQUIRED_FACT_RULES:
        assert rule.code.isupper()
        assert rule.code.startswith("PREFLIGHT_")
        assert getattr(pf, rule.code) == rule.code


def test_empty_object_is_never_accepted_as_a_fact():
    """`{}` 는 어떤 자리에서도 사실이 아니다. 감사 부정 사실 넷이 이 모양이었다."""
    checks = (
        (pf.verify_approval_repository, {"expected_repository": "x/y"}),
        (pf.verify_approval_ref, {"expected_ref": "refs/heads/main"}),
        (pf.verify_approval_commit, {"expected_commit": "a" * 40}),
        (pf.verify_ancestry, {}),
        (pf.verify_approver, {"expected_login": "x", "expected_id": 1}),
        (pf.verify_candidate_pull, {"expected_head": "a" * 40}),
        (pf.verify_candidate_commit,
         {"expected_commit": "a" * 40, "expected_tree": "b" * 40}),
        (pf.verify_candidate_repository, {"expected_repository": "x/y"}),
        (pf.verify_protected_branch, {"expected_head": "a" * 40}),
        (pf.verify_run, {"expected_run_id": 1, "expected_repository": "x/y"}),
        (pf.verify_environment, {"expected_name": "e"}),
        (pf.verify_branch_policies, {"expected_branch": "main"}),
        (pf.verify_contents_path, {"expected_path": "p"}),
    )
    for rule, expected in checks:
        for empty in ({}, None, [], "", 0):
            with pytest.raises(pf.FactRejected):
                rule(empty, **expected)
