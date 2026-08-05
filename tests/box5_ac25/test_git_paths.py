"""§6 경로 계산·glob 시험 + §11 경로 관련 시험."""
from __future__ import annotations

import subprocess

import pytest
from ac25 import git_paths
from ac25.git_paths import GitPathsError, match_glob


# ── glob 의미(§6) ──────────────────────────────────────────────────────
def test_star_does_not_cross_subdirectory():
    assert match_glob("a/*", "a/b")
    assert not match_glob("a/*", "a/b/c")


def test_doublestar_includes_subdirectories():
    assert match_glob("a/**", "a/b")
    assert match_glob("a/**", "a/b/c/d")


def test_glob_is_case_sensitive():
    assert match_glob("a/File.ts", "a/File.ts")
    assert not match_glob("a/File.ts", "a/file.ts")


# ── canonicalize(§6) ───────────────────────────────────────────────────
def test_invalid_path_encoding_is_rejected():
    with pytest.raises(GitPathsError) as e:
        git_paths.canonicalize_path(b"\xff\xfe not utf8")
    assert e.value.code == git_paths.CHANGED_PATH_ENCODING_INVALID


@pytest.mark.parametrize("bad", [b"/abs", b"a\\b", b"", b"a/../b", b"./a", b"a//b"])
def test_non_canonical_paths_are_rejected(bad):
    with pytest.raises(GitPathsError) as e:
        git_paths.canonicalize_path(bad)
    assert e.value.code in (
        git_paths.CHANGED_PATH_CANONICALIZATION_FAILED,
        git_paths.CHANGED_PATH_ENCODING_INVALID,
    )


# ── git diff NUL / 삭제 / rename(§6, §11) ──────────────────────────────
def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


def _init_repo(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    return repo


def _commit_all(repo, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         check=True, capture_output=True)
    return out.stdout.decode().strip()


@pytest.fixture()
def repo_with_changes(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "keep.txt").write_text("k\n")
    (repo / "del.txt").write_text("d\n")
    (repo / "old").mkdir()
    (repo / "old" / "name.txt").write_text("n\n")
    base = _commit_all(repo, "base")
    # head: 수정 + 추가 + 삭제 + rename(=삭제+추가, --no-renames)
    (repo / "keep.txt").write_text("k2\n")
    (repo / "added.txt").write_text("a\n")
    (repo / "del.txt").unlink()
    (repo / "old" / "name.txt").unlink()
    (repo / "new").mkdir()
    (repo / "new" / "name.txt").write_text("n\n")
    head = _commit_all(repo, "head")
    return repo, base, head


def test_nul_delimited_paths_are_parsed(repo_with_changes):
    repo, base, head = repo_with_changes
    changed = git_paths.compute_changed_paths(
        repository_path=str(repo), base_commit=base, head_commit=head)
    assert "keep.txt" in changed  # 수정 검출


def test_deleted_outside_path_is_reported(repo_with_changes):
    repo, base, head = repo_with_changes
    changed = git_paths.compute_changed_paths(
        repository_path=str(repo), base_commit=base, head_commit=head)
    assert "del.txt" in changed  # 삭제 경로 포함


def test_renamed_path_checks_old_and_new_paths(repo_with_changes):
    repo, base, head = repo_with_changes
    changed = git_paths.compute_changed_paths(
        repository_path=str(repo), base_commit=base, head_commit=head)
    # --no-renames 로 rename 은 양쪽 경로로 나타난다
    assert "old/name.txt" in changed and "new/name.txt" in changed


def test_outside_allowlist_lists_exact_paths(repo_with_changes):
    repo, base, head = repo_with_changes
    changed = git_paths.compute_changed_paths(
        repository_path=str(repo), base_commit=base, head_commit=head)
    res = git_paths.paths_outside_allowlist(changed, ("keep.txt",))
    assert "added.txt" in res.offending
    assert "keep.txt" in res.inside
