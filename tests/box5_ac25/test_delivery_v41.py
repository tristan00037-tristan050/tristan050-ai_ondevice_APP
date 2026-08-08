from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from ac25 import delivery_manifest as dm
from ac25 import strict_receipt as sr

pytestmark = pytest.mark.no_sidecar_token
BRANCH = "feat/box5-ac25-trusted-verification"


def run(cwd: Path, *argv: str, input_bytes=None) -> bytes:
    completed = subprocess.run(
        list(argv), cwd=cwd, input=input_bytes, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=True,
    )
    return completed.stdout


def make_delivery(tmp_path: Path):
    repo = tmp_path / "subject"
    repo.mkdir()
    run(repo, "git", "init", "-q")
    run(repo, "git", "config", "user.name", "AC25 Test")
    run(repo, "git", "config", "user.email", "ac25@example.invalid")
    (repo / "base.bin").write_bytes(b"base\x00bytes\n")
    run(repo, "git", "add", ".")
    run(repo, "git", "commit", "-q", "-m", "start")
    start = run(repo, "git", "rev-parse", "HEAD").decode().strip()
    run(repo, "git", "switch", "-q", "-c", BRANCH)
    (repo / "base.bin").write_bytes(b"target\x00bytes\n")
    (repo / "utf8-\ud55c\uae00.txt").write_text("ok\n", encoding="utf-8")
    run(repo, "git", "add", ".")
    run(repo, "git", "commit", "-q", "-m", "target")
    target = run(repo, "git", "rev-parse", "HEAD").decode().strip()
    tree = run(repo, "git", "show", "-s", "--format=%T", target).decode().strip()

    out = tmp_path / "AC25_R6_CLOSE_v41_DELIVERY"
    receipt = out / "AC25_R6_CLOSE_RECEIPT"
    receipt.mkdir(parents=True)
    (receipt / "evidence.txt").write_text("fixture\n", encoding="utf-8")
    (out / "START_HEAD").write_text(start + "\n", encoding="ascii")
    (out / "TARGET_HEAD").write_text(target + "\n", encoding="ascii")
    (out / "TARGET_TREE").write_text(tree + "\n", encoding="ascii")
    run(repo, "git", "bundle", "create", str(out / "candidate.bundle"), f"refs/heads/{BRANCH}", f"^{start}")
    patch = run(repo, "git", "diff", "--binary", "--full-index", "--no-ext-diff", start, target)
    (out / "cumulative.patch").write_bytes(patch)
    changed_nul = run(repo, "git", "diff", "--name-only", "-z", start, target)
    (out / "changed_paths.nul").write_bytes(changed_nul)
    changed = dm.changed_paths_document(changed_nul, base=start, head=target)
    (out / "changed_paths.json").write_bytes(sr.canonical_json_bytes(changed))
    (out / "README.md").write_text(
        "# AC25 R6 Close v4.1\n\n"
        "The literal reproduction commands are `git apply --index --binary cumulative.patch`, "
        "`git bundle verify candidate.bundle`, and `sha256sum --check DIGESTS.sha256`.\n",
        encoding="utf-8",
    )
    (out / "DIGESTS.sha256").write_bytes(dm.build_delivery_digests(out))
    return repo, out, start, target, tree


def patch_tree(repo: Path, out: Path, start: str, tmp_path: Path) -> str:
    work = tmp_path / "patch-reproduction"
    run(tmp_path, "git", "clone", "-q", str(repo), str(work))
    run(work, "git", "switch", "-q", "--detach", start)
    run(work, "git", "apply", "--index", "--binary", str(out / "cumulative.patch"))
    return run(work, "git", "write-tree").decode().strip()


def bundle_tree(repo: Path, out: Path, start: str, target: str, tmp_path: Path) -> str:
    work = tmp_path / "bundle-reproduction"
    work.mkdir()
    run(work, "git", "init", "-q")
    run(work, "git", "fetch", "-q", str(repo), start)
    run(work, "git", "bundle", "verify", str(out / "candidate.bundle"))
    run(work, "git", "fetch", "-q", str(out / "candidate.bundle"), f"refs/heads/{BRANCH}:refs/ac25/candidate")
    assert run(work, "git", "rev-parse", "refs/ac25/candidate").decode().strip() == target
    return run(work, "git", "show", "-s", "--format=%T", "refs/ac25/candidate").decode().strip()


def test_literal_readme_commands_reproduce_target_tree(tmp_path):
    repo, out, start, _target, tree = make_delivery(tmp_path)
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "git apply --index --binary cumulative.patch" in readme
    assert "git bundle verify candidate.bundle" in readme
    assert patch_tree(repo, out, start, tmp_path) == tree


def test_patch_and_bundle_converge_on_same_tree(tmp_path):
    repo, out, start, target, tree = make_delivery(tmp_path)
    assert patch_tree(repo, out, start, tmp_path) == tree
    assert bundle_tree(repo, out, start, target, tmp_path) == tree


def test_delivery_contains_only_declared_paths(tmp_path):
    _repo, out, _start, _target, _tree = make_delivery(tmp_path)
    files = dm.verify_delivery_layout(out)
    assert set(path for path in files if "/" not in path) == dm.DELIVERY_REQUIRED


def test_no_appledouble_or_resource_fork_entries(tmp_path):
    _repo, out, _start, _target, _tree = make_delivery(tmp_path)
    assert all(not Path(path).name.startswith("._") for path in dm.verify_delivery_layout(out))


def test_sha256sum_check_passes(tmp_path):
    _repo, out, _start, _target, _tree = make_delivery(tmp_path)
    dm.verify_delivery_digests(out)
    run(out, "sha256sum", "--check", "DIGESTS.sha256")


def test_start_head_is_ancestor_of_target_head(tmp_path):
    repo, _out, start, target, _tree = make_delivery(tmp_path)
    run(repo, "git", "merge-base", "--is-ancestor", start, target)
