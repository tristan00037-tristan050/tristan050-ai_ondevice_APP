"""§7 M-3 — 승인된 integration base 와 candidate head 의 결정론적 합성 merge.

감사 실측: refs/pull/903/merge 의 비후보 부모는 12d744b1… 인데 승인서의
integration baseline 은 afdb237e… 다. 그 참조는 GitHub 이 base 상태에 따라 언제든
다시 만드는 값이라, 그것에 결속하면 검증기는 항상 실패하고 단계 B 는 한 번도
돌지 못한다.

★판정 대상은 우리가 만든다. refs/pull/903/merge 는 참고값으로만 관측한다.

★`git merge --no-ff --no-commit` 상태를 commit 이라고 부르지 않는다.
  그 상태에는 커밋이 없다. write-tree → commit-tree 로 실제 커밋을 만들고,
  커밋 신원(이름·메일·시각·메시지)을 고정해 같은 입력이면 같은 해시가 나오게 한다.

모든 git 호출은 argv 배열과 shell=False 를 쓴다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# ── 오류 코드 (§7) ─────────────────────────────────────────────────────
INTEGRATION_BASE_FETCH_FAILED = "INTEGRATION_BASE_FETCH_FAILED"
INTEGRATION_CANDIDATE_FETCH_FAILED = "INTEGRATION_CANDIDATE_FETCH_FAILED"
INTEGRATION_OBJECT_NOT_COMMIT = "INTEGRATION_OBJECT_NOT_COMMIT"
INTEGRATION_WORKTREE_INVALID = "INTEGRATION_WORKTREE_INVALID"
INTEGRATION_MERGE_CONFLICT = "INTEGRATION_MERGE_CONFLICT"
INTEGRATION_UNMERGED_INDEX = "INTEGRATION_UNMERGED_INDEX"
INTEGRATION_TREE_WRITE_FAILED = "INTEGRATION_TREE_WRITE_FAILED"
INTEGRATION_COMMIT_CREATE_FAILED = "INTEGRATION_COMMIT_CREATE_FAILED"
INTEGRATION_MERGE_TREE_MISMATCH = "INTEGRATION_MERGE_TREE_MISMATCH"
INTEGRATION_MERGE_PARENT_MISMATCH = "INTEGRATION_MERGE_PARENT_MISMATCH"
INTEGRATION_CLEANUP_FAILED = "INTEGRATION_CLEANUP_FAILED"

_OID_RE = re.compile(r"\A[0-9a-f]{40}\Z")

# ★커밋 신원 고정 — 같은 입력이면 같은 커밋 해시가 나와야 한다.
COMMITTER_NAME = "Butler AC25 Verifier"
COMMITTER_EMAIL = "ac25-verifier@invalid"
COMMITTER_DATE = "2000-01-01T00:00:00Z"
MERGE_MESSAGE = "Butler AC-25 deterministic integration tree"

_FIXED_ENV = {
    "GIT_AUTHOR_NAME": COMMITTER_NAME,
    "GIT_AUTHOR_EMAIL": COMMITTER_EMAIL,
    "GIT_AUTHOR_DATE": COMMITTER_DATE,
    "GIT_COMMITTER_NAME": COMMITTER_NAME,
    "GIT_COMMITTER_EMAIL": COMMITTER_EMAIL,
    "GIT_COMMITTER_DATE": COMMITTER_DATE,
}


class IntegrationMergeError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SyntheticMerge:
    integration_base_commit: str
    candidate_head: str
    merge_tree: str
    synthetic_merge_commit: str
    parents: tuple[str, str]
    worktree: Path
    github_merge_ref_observed: str | None


def _git(
    repository: Path, args: list[str], *, env_extra: dict | None = None
) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env.update(_FIXED_ENV)
    if env_extra:
        env.update(env_extra)
    # ★argv 배열 · shell=False. 동적 문자열 조립을 하지 않는다.
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _require_oid(value: str, code: str) -> str:
    if _OID_RE.match(value or "") is None:
        raise IntegrationMergeError(code, "40자 소문자 hex OID 아님")
    return value


def _object_type(repository: Path, oid: str) -> str | None:
    done = _git(repository, ["cat-file", "-t", oid])
    return done.stdout.strip() if done.returncode == 0 else None


def observe_github_merge_ref(repository: Path, pr_number: int) -> str | None:
    """refs/pull/N/merge 를 ★참고값으로만★ 관측한다. 판정에 쓰지 않는다."""
    fetched = _git(
        repository, ["fetch", "--no-tags", "origin", f"refs/pull/{pr_number}/merge"]
    )
    if fetched.returncode != 0:
        return None
    resolved = _git(repository, ["rev-parse", "FETCH_HEAD"])
    if resolved.returncode != 0:
        return None
    observed = resolved.stdout.strip()
    return observed if _OID_RE.match(observed) else None


def build_synthetic_merge(
    *,
    repository: Path,
    destination: Path,
    integration_base_commit: str,
    candidate_head: str,
    github_merge_ref_observed: str | None = None,
) -> SyntheticMerge:
    """승인된 base 와 후보 head 로 판정 대상 tree·commit 을 직접 합성한다."""
    # 1. 두 OID strict 검증
    base = _require_oid(integration_base_commit, INTEGRATION_BASE_FETCH_FAILED)
    head = _require_oid(candidate_head, INTEGRATION_CANDIDATE_FETCH_FAILED)

    # 2. exact SHA fetch (이미 있으면 넘어간다)
    for oid, code in ((base, INTEGRATION_BASE_FETCH_FAILED),
                      (head, INTEGRATION_CANDIDATE_FETCH_FAILED)):
        if _object_type(repository, oid) is None:
            fetched = _git(repository, ["fetch", "--no-tags", "origin", oid])
            if fetched.returncode != 0:
                raise IntegrationMergeError(code, oid)

    # 3. commit 객체 확인
    for oid in (base, head):
        if _object_type(repository, oid) != "commit":
            raise IntegrationMergeError(INTEGRATION_OBJECT_NOT_COMMIT, oid)

    # 4. 전용 임시 destination 확인
    if destination.exists():
        raise IntegrationMergeError(INTEGRATION_WORKTREE_INVALID, "destination 이 이미 있다")
    destination.parent.mkdir(parents=True, exist_ok=True)

    added = False
    try:
        # 5. base detached worktree 생성
        created = _git(
            repository, ["worktree", "add", "--detach", str(destination), base]
        )
        if created.returncode != 0:
            raise IntegrationMergeError(
                INTEGRATION_WORKTREE_INVALID, created.stderr.strip()[:200]
            )
        added = True

        # 6. candidate 를 --no-ff --no-commit 병합
        merged = _git(destination, ["merge", "--no-ff", "--no-commit", head])
        if merged.returncode != 0:
            raise IntegrationMergeError(
                INTEGRATION_MERGE_CONFLICT, merged.stdout.strip()[:200]
            )

        # 7. conflict 와 unmerged index 0 확인
        unmerged = _git(destination, ["diff", "--name-only", "--diff-filter=U"])
        if unmerged.returncode != 0 or unmerged.stdout.strip():
            raise IntegrationMergeError(INTEGRATION_UNMERGED_INDEX, "unmerged entry 존재")
        listed = _git(destination, ["ls-files", "--unmerged"])
        if listed.returncode != 0 or listed.stdout.strip():
            raise IntegrationMergeError(INTEGRATION_UNMERGED_INDEX, "index 에 unmerged stage 존재")

        # 8. write-tree 로 merge_tree 생성 (★여기서 처음으로 tree 가 생긴다)
        written = _git(destination, ["write-tree"])
        if written.returncode != 0:
            raise IntegrationMergeError(
                INTEGRATION_TREE_WRITE_FAILED, written.stderr.strip()[:200]
            )
        merge_tree = written.stdout.strip()
        if _OID_RE.match(merge_tree) is None:
            raise IntegrationMergeError(INTEGRATION_TREE_WRITE_FAILED, merge_tree[:64])

        # 9. commit-tree 로 두 부모 commit 생성 (★비로소 commit 이다)
        created_commit = _git(
            destination,
            ["commit-tree", merge_tree, "-p", base, "-p", head, "-m", MERGE_MESSAGE],
        )
        if created_commit.returncode != 0:
            raise IntegrationMergeError(
                INTEGRATION_COMMIT_CREATE_FAILED, created_commit.stderr.strip()[:200]
            )
        merge_commit = created_commit.stdout.strip()
        if _OID_RE.match(merge_commit) is None:
            raise IntegrationMergeError(INTEGRATION_COMMIT_CREATE_FAILED, merge_commit[:64])

        # 10. tree 와 부모 순서 재검증
        observed_tree = _git(destination, ["show", "-s", "--format=%T", merge_commit])
        if observed_tree.returncode != 0 or observed_tree.stdout.strip() != merge_tree:
            raise IntegrationMergeError(
                INTEGRATION_MERGE_TREE_MISMATCH,
                f"{observed_tree.stdout.strip()} != {merge_tree}",
            )
        observed_parents = _git(destination, ["show", "-s", "--format=%P", merge_commit])
        parents = tuple(observed_parents.stdout.split())
        if observed_parents.returncode != 0 or parents != (base, head):
            raise IntegrationMergeError(
                INTEGRATION_MERGE_PARENT_MISMATCH, " ".join(parents)[:120]
            )

        return SyntheticMerge(
            integration_base_commit=base,
            candidate_head=head,
            merge_tree=merge_tree,
            synthetic_merge_commit=merge_commit,
            parents=(base, head),
            worktree=destination,
            github_merge_ref_observed=github_merge_ref_observed,
        )
    except Exception:
        if added:
            cleanup_worktree(repository, destination, raise_on_failure=False)
        raise


def cleanup_worktree(
    repository: Path, destination: Path, *, raise_on_failure: bool = True
) -> None:
    """12. finally cleanup."""
    removed = _git(repository, ["worktree", "remove", "--force", str(destination)])
    if removed.returncode != 0 and destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    _git(repository, ["worktree", "prune"])
    if raise_on_failure and destination.exists():
        raise IntegrationMergeError(INTEGRATION_CLEANUP_FAILED, str(destination))


__all__ = [
    "COMMITTER_DATE",
    "COMMITTER_EMAIL",
    "COMMITTER_NAME",
    "INTEGRATION_BASE_FETCH_FAILED",
    "INTEGRATION_CANDIDATE_FETCH_FAILED",
    "INTEGRATION_CLEANUP_FAILED",
    "INTEGRATION_COMMIT_CREATE_FAILED",
    "INTEGRATION_MERGE_CONFLICT",
    "INTEGRATION_MERGE_PARENT_MISMATCH",
    "INTEGRATION_MERGE_TREE_MISMATCH",
    "INTEGRATION_OBJECT_NOT_COMMIT",
    "INTEGRATION_TREE_WRITE_FAILED",
    "INTEGRATION_UNMERGED_INDEX",
    "INTEGRATION_WORKTREE_INVALID",
    "MERGE_MESSAGE",
    "IntegrationMergeError",
    "SyntheticMerge",
    "build_synthetic_merge",
    "cleanup_worktree",
    "observe_github_merge_ref",
]
