"""§15 M-3 — 결정론적 합성 merge 시험.

감사 실측: refs/pull/903/merge 의 비후보 부모는 12d744b1… 인데 승인 baseline 은
afdb237e… 다. 그 참조에 결속하면 검증기는 항상 실패한다.
★판정 대상은 우리가 만든다.

합성 저장소를 만들어 시험한다. 네트워크를 쓰지 않는다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from ac25 import integration_merge as im

pytestmark = pytest.mark.no_sidecar_token


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    """base 에서 갈라진 두 갈래. 충돌하지 않게 서로 다른 파일을 바꾼다."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")

    (root / "shared.txt").write_text("shared\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "root")
    fork = _git(root, "rev-parse", "HEAD")

    (root / "base-side.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base side")
    base = _git(root, "rev-parse", "HEAD")

    _git(root, "checkout", "-q", "--detach", fork)
    (root / "candidate-side.txt").write_text("candidate\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "candidate side")
    candidate = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "main")

    return {"root": root, "fork": fork, "base": base, "candidate": candidate}


@pytest.fixture
def conflicting(tmp_path: Path) -> dict:
    """양쪽이 ★같은 줄★ 을 다르게 바꾼다."""
    root = tmp_path / "conflict"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "same.txt").write_text("original\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "root")
    fork = _git(root, "rev-parse", "HEAD")

    (root / "same.txt").write_text("base version\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")

    _git(root, "checkout", "-q", "--detach", fork)
    (root / "same.txt").write_text("candidate version\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "candidate")
    candidate = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "main")
    return {"root": root, "base": base, "candidate": candidate}


def _build(repo, destination_name="wt", **overrides):
    values = {
        "repository": repo["root"],
        "destination": repo["root"].parent / destination_name,
        "integration_base_commit": repo["base"],
        "candidate_head": repo["candidate"],
    }
    values.update(overrides)
    return im.build_synthetic_merge(**values)


# ══ 정상 통과 · 부모 순서 · tree 일치 ══════════════════════════════════
def test_synthetic_merge_has_correct_parent_order(repo):
    merge = _build(repo)
    try:
        assert merge.parents == (repo["base"], repo["candidate"])
        assert merge.integration_base_commit == repo["base"]
        assert merge.candidate_head == repo["candidate"]
    finally:
        im.cleanup_worktree(repo["root"], merge.worktree, raise_on_failure=False)


def test_commit_tree_matches_write_tree(repo):
    merge = _build(repo)
    try:
        observed = _git(repo["root"], "show", "-s", "--format=%T", merge.synthetic_merge_commit)
        assert observed == merge.merge_tree
    finally:
        im.cleanup_worktree(repo["root"], merge.worktree, raise_on_failure=False)


def test_merge_commit_is_a_real_commit_object(repo):
    """★--no-commit 상태를 commit 이라 부르지 않는다. 진짜 객체가 있어야 한다."""
    merge = _build(repo)
    try:
        kind = _git(repo["root"], "cat-file", "-t", merge.synthetic_merge_commit)
        assert kind == "commit"
        parents = _git(repo["root"], "show", "-s", "--format=%P", merge.synthetic_merge_commit)
        assert parents.split() == [repo["base"], repo["candidate"]]
    finally:
        im.cleanup_worktree(repo["root"], merge.worktree, raise_on_failure=False)


def test_result_contains_both_changes(repo):
    merge = _build(repo)
    try:
        listing = _git(repo["root"], "ls-tree", "-r", "--name-only", merge.merge_tree)
        assert "base-side.txt" in listing
        assert "candidate-side.txt" in listing
    finally:
        im.cleanup_worktree(repo["root"], merge.worktree, raise_on_failure=False)


# ══ 재현성 ═════════════════════════════════════════════════════════════
def test_same_input_yields_same_commit_and_tree(repo):
    first = _build(repo, "wt1")
    im.cleanup_worktree(repo["root"], first.worktree, raise_on_failure=False)
    second = _build(repo, "wt2")
    im.cleanup_worktree(repo["root"], second.worktree, raise_on_failure=False)
    assert first.synthetic_merge_commit == second.synthetic_merge_commit
    assert first.merge_tree == second.merge_tree


def test_commit_identity_is_pinned():
    assert im.COMMITTER_NAME == "Butler AC25 Verifier"
    assert im.COMMITTER_EMAIL == "ac25-verifier@invalid"
    assert im.COMMITTER_DATE == "2000-01-01T00:00:00Z"
    assert im.MERGE_MESSAGE == "Butler AC-25 deterministic integration tree"


def test_changing_the_candidate_changes_the_result(repo):
    first = _build(repo, "wt1")
    im.cleanup_worktree(repo["root"], first.worktree, raise_on_failure=False)

    _git(repo["root"], "checkout", "-q", "--detach", repo["candidate"])
    (repo["root"] / "candidate-side.txt").write_text("changed\n", encoding="utf-8")
    _git(repo["root"], "add", "-A")
    _git(repo["root"], "commit", "-q", "-m", "candidate moved")
    moved = _git(repo["root"], "rev-parse", "HEAD")
    _git(repo["root"], "checkout", "-q", "main")

    second = _build(repo, "wt2", candidate_head=moved)
    im.cleanup_worktree(repo["root"], second.worktree, raise_on_failure=False)
    assert second.merge_tree != first.merge_tree


def test_changing_the_base_changes_the_result(repo):
    first = _build(repo, "wt1")
    im.cleanup_worktree(repo["root"], first.worktree, raise_on_failure=False)

    (repo["root"] / "base-side.txt").write_text("base moved\n", encoding="utf-8")
    _git(repo["root"], "add", "-A")
    _git(repo["root"], "commit", "-q", "-m", "base moved")
    moved = _git(repo["root"], "rev-parse", "HEAD")

    second = _build(repo, "wt2", integration_base_commit=moved)
    im.cleanup_worktree(repo["root"], second.worktree, raise_on_failure=False)
    assert second.merge_tree != first.merge_tree
    assert second.parents[0] == moved


# ══ fetch 실패 · non-commit · conflict ═════════════════════════════════
@pytest.mark.parametrize("field", ["integration_base_commit", "candidate_head"])
def test_malformed_oid_is_rejected(repo, field):
    with pytest.raises(im.IntegrationMergeError) as caught:
        _build(repo, **{field: "not-an-oid"})
    assert caught.value.code in {
        im.INTEGRATION_BASE_FETCH_FAILED, im.INTEGRATION_CANDIDATE_FETCH_FAILED
    }


def test_unknown_commit_is_fetch_failure(repo):
    with pytest.raises(im.IntegrationMergeError) as caught:
        _build(repo, candidate_head="0" * 40)
    assert caught.value.code == im.INTEGRATION_CANDIDATE_FETCH_FAILED


def test_non_commit_object_is_rejected(repo):
    blob = _git(repo["root"], "rev-parse", "HEAD^{tree}")
    with pytest.raises(im.IntegrationMergeError) as caught:
        _build(repo, candidate_head=blob)
    assert caught.value.code in {
        im.INTEGRATION_OBJECT_NOT_COMMIT, im.INTEGRATION_CANDIDATE_FETCH_FAILED
    }


def test_conflict_is_blocked(conflicting):
    with pytest.raises(im.IntegrationMergeError) as caught:
        _build(conflicting)
    assert caught.value.code in {
        im.INTEGRATION_MERGE_CONFLICT, im.INTEGRATION_UNMERGED_INDEX
    }


def test_conflict_leaves_no_worktree_behind(conflicting):
    destination = conflicting["root"].parent / "wt"
    with pytest.raises(im.IntegrationMergeError):
        _build(conflicting)
    assert not destination.exists()


def test_existing_destination_is_rejected(repo):
    destination = repo["root"].parent / "occupied"
    destination.mkdir()
    with pytest.raises(im.IntegrationMergeError) as caught:
        _build(repo, "occupied")
    assert caught.value.code == im.INTEGRATION_WORKTREE_INVALID


# ══ GitHub merge ref 무관성 ════════════════════════════════════════════
def test_github_merge_ref_is_carried_but_not_used(repo):
    merge = _build(repo, github_merge_ref_observed="5" * 40)
    try:
        assert merge.github_merge_ref_observed == "5" * 40
        assert merge.synthetic_merge_commit != "5" * 40
        assert "5" * 40 not in merge.parents
    finally:
        im.cleanup_worktree(repo["root"], merge.worktree, raise_on_failure=False)


def test_result_is_identical_regardless_of_observed_merge_ref(repo):
    first = _build(repo, "wt1", github_merge_ref_observed=None)
    im.cleanup_worktree(repo["root"], first.worktree, raise_on_failure=False)
    second = _build(repo, "wt2", github_merge_ref_observed="a" * 40)
    im.cleanup_worktree(repo["root"], second.worktree, raise_on_failure=False)
    assert first.synthetic_merge_commit == second.synthetic_merge_commit


def test_observing_merge_ref_never_raises_on_missing_ref(repo):
    assert im.observe_github_merge_ref(repo["root"], 999999) is None


# ══ cleanup ════════════════════════════════════════════════════════════
def test_cleanup_removes_the_worktree(repo):
    merge = _build(repo)
    assert merge.worktree.exists()
    im.cleanup_worktree(repo["root"], merge.worktree)
    assert not merge.worktree.exists()


# ══ shell 사용 0 ═══════════════════════════════════════════════════════
def test_no_shell_true_anywhere():
    import inspect

    source = inspect.getsource(im)
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "bash -c" not in source
