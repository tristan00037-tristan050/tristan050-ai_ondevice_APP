"""§E6-1 원격 사실 수집 시험.

지시 6번이 요구한 여덟 갈래를 모두 덮는다.
  정상 · 404 · 403 · rate-limit · 잘못된 JSON · branch 이동 · 비조상 commit · pagination

전송 계층은 가짜를 주입한다. 네트워크를 쓰지 않는다.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest
from ac25 import remote_facts as rf

pytestmark = pytest.mark.no_sidecar_token

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DOC = (FIXTURES / "approval_document.md").read_bytes()
SIG = (FIXTURES / "approval_document.md.sig").read_bytes()
SIGNERS = (FIXTURES / "allowed_signers").read_bytes()

APPROVAL_REPO = "owner/approval"
CANDIDATE_REPO = "owner/candidate"
PROTECTED_REF = "refs/heads/main"
MAIN_HEAD = "a" * 40
APPROVAL_COMMIT = "c" * 40
CANDIDATE_HEAD = "6" * 40
CANDIDATE_TREE = "3" * 40
CANDIDATE_BASE = "b" * 40

DOC_PATH = "docs/decisions/교차트랙승인.md"
SIG_PATH = "docs/decisions/교차트랙승인.md.sig"
SIGNERS_PATH = "docs/decisions/allowed_signers"


def _content(data: bytes, path: str) -> dict:
    return {
        "path": path,
        "encoding": "base64",
        "content": base64.b64encode(data).decode("ascii"),
    }


def _ok(payload) -> rf.TransportResult:
    return rf.TransportResult(status=200, payload=payload)


class FakeGitHub:
    """고정된 응답표를 돌려주는 가짜 전송. 요청 경로를 기록한다."""

    def __init__(self, *, main_head: str = MAIN_HEAD, compare_status: str = "behind") -> None:
        self.main_head = main_head
        self.compare_status = compare_status
        self.overrides: dict[str, rf.TransportResult] = {}
        self.requested: list[str] = []

    def table(self) -> dict[str, rf.TransportResult]:
        return {
            f"repos/{APPROVAL_REPO}": _ok({"full_name": APPROVAL_REPO}),
            f"repos/{APPROVAL_REPO}/git/ref/heads/main": _ok(
                {"ref": PROTECTED_REF, "object": {"sha": self.main_head}}
            ),
            f"repos/{APPROVAL_REPO}/commits/{APPROVAL_COMMIT}": _ok(
                {"sha": APPROVAL_COMMIT, "commit": {"committer": {"date": "2026-08-05T04:48:43Z"}}}
            ),
            f"repos/{APPROVAL_REPO}/compare/{self.main_head}...{APPROVAL_COMMIT}": _ok(
                {"status": self.compare_status}
            ),
            f"repos/{APPROVAL_REPO}/contents/docs/decisions/"
            f"%EA%B5%90%EC%B0%A8%ED%8A%B8%EB%9E%99%EC%8A%B9%EC%9D%B8.md"
            f"?ref={APPROVAL_COMMIT}": _ok(_content(DOC, DOC_PATH)),
            f"repos/{APPROVAL_REPO}/contents/docs/decisions/"
            f"%EA%B5%90%EC%B0%A8%ED%8A%B8%EB%9E%99%EC%8A%B9%EC%9D%B8.md.sig"
            f"?ref={APPROVAL_COMMIT}": _ok(_content(SIG, SIG_PATH)),
            f"repos/{APPROVAL_REPO}/contents/{SIGNERS_PATH}?ref={APPROVAL_COMMIT}": _ok(
                _content(SIGNERS, SIGNERS_PATH)
            ),
            f"repos/{CANDIDATE_REPO}/actions/runs/77": _ok(
                {"run_started_at": "2026-08-05T05:00:00Z"}
            ),
            f"repos/{CANDIDATE_REPO}/pulls/903": _ok(
                {"head": {"sha": CANDIDATE_HEAD}, "base": {"sha": CANDIDATE_BASE}}
            ),
            f"repos/{CANDIDATE_REPO}/git/commits/{CANDIDATE_HEAD}": _ok(
                {"tree": {"sha": CANDIDATE_TREE}}
            ),
            f"users/approver": _ok({"id": 4242}),
        }

    def __call__(self, path: str) -> rf.TransportResult:
        self.requested.append(path)
        if path in self.overrides:
            return self.overrides[path]
        return self.table().get(path, rf.TransportResult(status=404, message="not in table"))


def _collect(transport):
    return rf.collect_remote_facts(
        transport=transport,
        approval_repository=APPROVAL_REPO,
        approval_protected_ref=PROTECTED_REF,
        approval_commit_sha=APPROVAL_COMMIT,
        document_path=DOC_PATH,
        signature_path=SIG_PATH,
        allowed_signers_path=SIGNERS_PATH,
        candidate_repository=CANDIDATE_REPO,
        pr_number=903,
        run_repository=CANDIDATE_REPO,
        run_id=77,
    )


# ── 정상 ───────────────────────────────────────────────────────────────
def test_happy_path_collects_every_fact():
    observation, errors = _collect(FakeGitHub())
    assert errors == ()
    facts = observation.facts
    assert facts.approval_commit_fetchable is True
    assert facts.approval_commit_reachable is True
    assert facts.approval_committer_utc == "2026-08-05T04:48:43Z"
    assert facts.run_started_at == "2026-08-05T05:00:00Z"
    assert hashlib.sha256(facts.document_bytes).hexdigest() == hashlib.sha256(DOC).hexdigest()
    assert facts.signature_bytes == SIG
    assert facts.allowed_signers_bytes == SIGNERS
    assert observation.protected_ref_head == MAIN_HEAD
    assert observation.observed_repository == APPROVAL_REPO
    assert observation.observed_protected_ref == PROTECTED_REF
    assert observation.observed_document_path == DOC_PATH
    assert observation.candidate_head_sha == CANDIDATE_HEAD
    assert observation.candidate_head_tree == CANDIDATE_TREE
    assert observation.candidate_base_sha == CANDIDATE_BASE
    # 승인자 ID 는 여기서 확정하지 않는다(문서를 읽은 뒤 조회한다)
    assert facts.approver_id_for_login is None


def test_document_path_is_percent_encoded():
    transport = FakeGitHub()
    _collect(transport)
    assert any("%EA%B5%90" in path for path in transport.requested)


# ── 404 · 403 · rate-limit · 잘못된 JSON ───────────────────────────────
@pytest.mark.parametrize(
    ("result", "expected_code"),
    [
        (rf.TransportResult(status=404, message="Not Found"), rf.REMOTE_FACT_NOT_FOUND),
        (
            rf.TransportResult(status=403, headers={"x-ratelimit-remaining": "12"}),
            rf.REMOTE_FACT_FORBIDDEN,
        ),
        (
            rf.TransportResult(status=403, headers={"x-ratelimit-remaining": "0"}),
            rf.REMOTE_FACT_RATE_LIMITED,
        ),
        (rf.TransportResult(status=429), rf.REMOTE_FACT_RATE_LIMITED),
        (rf.TransportResult(status=200, payload=None, message="JSON 파싱 실패"),
         rf.REMOTE_FACT_MALFORMED),
        (rf.TransportResult(status=500, message="server error"), rf.REMOTE_FACT_UNAVAILABLE),
    ],
)
def test_transport_status_is_classified(result, expected_code):
    assert rf.classify(result) == expected_code


@pytest.mark.parametrize(
    ("result", "expected_code"),
    [
        (rf.TransportResult(status=404), rf.REMOTE_FACT_NOT_FOUND),
        (rf.TransportResult(status=403), rf.REMOTE_FACT_FORBIDDEN),
        (
            rf.TransportResult(status=403, headers={"x-ratelimit-remaining": "0"}),
            rf.REMOTE_FACT_RATE_LIMITED,
        ),
        (rf.TransportResult(status=200, payload=None), rf.REMOTE_FACT_MALFORMED),
    ],
)
def test_approval_document_failure_is_reported_with_its_own_code(result, expected_code):
    transport = FakeGitHub()
    key = (
        f"repos/{APPROVAL_REPO}/contents/docs/decisions/"
        f"%EA%B5%90%EC%B0%A8%ED%8A%B8%EB%9E%99%EC%8A%B9%EC%9D%B8.md?ref={APPROVAL_COMMIT}"
    )
    transport.overrides[key] = result
    observation, errors = _collect(transport)
    assert observation.facts.document_bytes is None
    assert expected_code in {e.code for e in errors}
    # 실패에는 반드시 증거가 붙는다
    assert all(e.expected or e.observed for e in errors)


def test_malformed_json_body_never_yields_bytes():
    transport = FakeGitHub()
    key = f"repos/{APPROVAL_REPO}/contents/{SIGNERS_PATH}?ref={APPROVAL_COMMIT}"
    transport.overrides[key] = rf.TransportResult(status=200, payload=None, message="bad json")
    observation, errors = _collect(transport)
    assert observation.facts.allowed_signers_bytes is None
    assert rf.REMOTE_FACT_MALFORMED in {e.code for e in errors}


# ── branch 이동 ────────────────────────────────────────────────────────
def test_ancestry_is_judged_against_the_pinned_protected_head():
    """보호 ref 가 움직여도 판정 기준 커밋이 무엇이었는지 영수증에 남는다."""
    moved = "f" * 40
    transport = FakeGitHub(main_head=moved, compare_status="behind")
    observation, errors = _collect(transport)
    assert errors == ()
    assert observation.protected_ref_head == moved
    assert observation.facts.approval_commit_reachable is True
    # 판정에 쓴 compare 요청이 ★그 커밋★ 기준이었는지 확인
    assert f"repos/{APPROVAL_REPO}/compare/{moved}...{APPROVAL_COMMIT}" in transport.requested


def test_branch_move_that_drops_the_commit_is_not_reachable():
    transport = FakeGitHub(main_head="f" * 40, compare_status="diverged")
    observation, _ = _collect(transport)
    assert observation.facts.approval_commit_reachable is False


def test_unreadable_protected_ref_blocks_reachability():
    transport = FakeGitHub()
    transport.overrides[f"repos/{APPROVAL_REPO}/git/ref/heads/main"] = rf.TransportResult(status=404)
    observation, errors = _collect(transport)
    assert observation.protected_ref_head == ""
    assert observation.facts.approval_commit_reachable is False
    assert rf.REMOTE_FACT_NOT_FOUND in {e.code for e in errors}


# ── 비조상 commit ──────────────────────────────────────────────────────
@pytest.mark.parametrize("status", ["ahead", "diverged"])
def test_non_ancestor_commit_is_rejected(status):
    transport = FakeGitHub(compare_status=status)
    observation, _ = _collect(transport)
    assert observation.facts.approval_commit_reachable is False


@pytest.mark.parametrize("status", ["behind", "identical"])
def test_ancestor_states_are_accepted(status):
    transport = FakeGitHub(compare_status=status)
    observation, _ = _collect(transport)
    assert observation.facts.approval_commit_reachable is True


def test_is_ancestor_asks_compare_in_the_right_direction():
    seen: list[str] = []

    def transport(path: str) -> rf.TransportResult:
        seen.append(path)
        return _ok({"status": "behind"})

    assert rf.is_ancestor(
        transport=transport, repository=APPROVAL_REPO,
        ancestor=APPROVAL_COMMIT, descendant=MAIN_HEAD,
    ) is True
    # base=후손, head=조상 순서여야 status 의미가 맞는다
    assert seen == [f"repos/{APPROVAL_REPO}/compare/{MAIN_HEAD}...{APPROVAL_COMMIT}"]


def test_unparseable_compare_response_is_not_a_pass():
    assert rf.is_ancestor(
        transport=lambda path: _ok({"status": 12}),
        repository=APPROVAL_REPO, ancestor=APPROVAL_COMMIT, descendant=MAIN_HEAD,
    ) is None
    assert rf.is_ancestor(
        transport=lambda path: rf.TransportResult(status=403),
        repository=APPROVAL_REPO, ancestor=APPROVAL_COMMIT, descendant=MAIN_HEAD,
    ) is None


# ── pagination ─────────────────────────────────────────────────────────
def test_commit_list_endpoint_is_never_used_for_reachability():
    """구판은 `commits?sha=` 목록이 비지 않는지로 도달 가능을 근사했다.

    그 조회는 페이지 하나만 봐도 늘 비지 않으므로 저장소에 존재하기만 하면
    통과한다. 근사 검사는 삭제됐고, 목록을 아무리 채워도 조상이 되지 않는다.
    """
    transport = FakeGitHub(compare_status="ahead")
    # 목록 응답을 넉넉히(=페이지가 가득 찬 것처럼) 준다
    transport.overrides[f"repos/{APPROVAL_REPO}/commits?sha={APPROVAL_COMMIT}&per_page=1"] = _ok(
        [{"sha": APPROVAL_COMMIT}] * 100
    )
    observation, _ = _collect(transport)
    assert observation.facts.approval_commit_reachable is False
    assert not any("commits?sha=" in path for path in transport.requested)


def test_list_payload_where_object_expected_is_malformed_not_truthy():
    transport = FakeGitHub()
    transport.overrides[f"repos/{APPROVAL_REPO}/commits/{APPROVAL_COMMIT}"] = _ok(
        [{"sha": APPROVAL_COMMIT}]
    )
    observation, errors = _collect(transport)
    assert observation.facts.approval_commit_fetchable is False
    assert rf.REMOTE_FACT_MALFORMED in {e.code for e in errors}


# ── 승인자 조회는 문서를 읽은 뒤 따로 한다 ─────────────────────────────
def test_read_account_id_returns_real_id():
    account_id, errors = rf.read_account_id(transport=FakeGitHub(), login="approver")
    assert account_id == 4242
    assert errors == ()


def test_read_account_id_fails_closed_on_missing_user():
    account_id, errors = rf.read_account_id(transport=FakeGitHub(), login="ghost")
    assert account_id is None
    assert rf.REMOTE_FACT_NOT_FOUND in {e.code for e in errors}


def test_read_account_id_rejects_empty_login():
    account_id, errors = rf.read_account_id(transport=FakeGitHub(), login="")
    assert account_id is None
    assert errors != ()


def test_boolean_id_is_not_accepted_as_account_id():
    transport = FakeGitHub()
    transport.overrides["users/approver"] = _ok({"id": True})
    account_id, errors = rf.read_account_id(transport=transport, login="approver")
    assert account_id is None
    assert errors != ()


# ── 후보 좌표 ──────────────────────────────────────────────────────────
def test_candidate_head_reads_sha_tree_and_base():
    sha, tree, base = rf.read_candidate_head(
        transport=FakeGitHub(), repository=CANDIDATE_REPO, pr_number=903
    )
    assert (sha, tree, base) == (CANDIDATE_HEAD, CANDIDATE_TREE, CANDIDATE_BASE)


def test_candidate_head_missing_pr_is_all_none():
    transport = FakeGitHub()
    transport.overrides[f"repos/{CANDIDATE_REPO}/pulls/903"] = rf.TransportResult(status=404)
    assert rf.read_candidate_head(
        transport=transport, repository=CANDIDATE_REPO, pr_number=903
    ) == (None, None, None)
