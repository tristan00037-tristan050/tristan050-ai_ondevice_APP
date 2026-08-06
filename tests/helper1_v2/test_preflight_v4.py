from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "helper1_preflight.py"


def _module():
    spec = importlib.util.spec_from_file_location("helper1_preflight_v4", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_policy_is_immutable_and_exact() -> None:
    module = _module()
    policy = module._policy()
    assert policy["repository_id"] == 1097940756
    assert policy["base_commit"] == "390af710bdc76a58be3158b6bcbf0638d62b49a4"
    assert policy["base_tree"] == "dfbd96c3055dad43024861543530d7e0e1469b5f"
    assert policy["reconstructed_tree"] == "b1fe153f0c14342f0f512d0d0ea39337104aae28"


def test_overlay_manifest_rejects_digest_mismatch(tmp_path: Path) -> None:
    module = _module()
    manifest = tmp_path / "overlay.json"
    manifest.write_text('{"file_count":0,"files":[]}', encoding="utf-8")
    try:
        module._manifest(manifest, "0" * 64)
    except module.PreflightError as error:
        assert str(error) == "BLOCK_OVERLAY_DIGEST_MISMATCH"
    else:
        raise AssertionError("mismatched overlay digest was accepted")


def _run(repository: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def test_deterministic_tar_has_no_appledouble_and_matches_patch_tree(
    tmp_path: Path,
) -> None:
    module = _module()
    repository = tmp_path / "source"
    repository.mkdir()
    _run(repository, "init", "--quiet")
    _run(repository, "config", "user.name", "Helper1 Test")
    _run(repository, "config", "user.email", "helper1@example.invalid")
    (repository / "base.txt").write_text("base\n", encoding="utf-8")
    _run(repository, "add", "base.txt")
    _run(repository, "commit", "--quiet", "-m", "base")

    (repository / "base.txt").write_text("corrected\n", encoding="utf-8")
    tool = repository / "nested" / "tool.sh"
    tool.parent.mkdir()
    tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tool.chmod(0o755)
    _run(repository, "add", "--intent-to-add", "nested/tool.sh")

    records = {}
    for relative in ("base.txt", "nested/tool.sh"):
        path = repository / relative
        payload = path.read_bytes()
        records[relative] = {
            "path": relative,
            "kind": "file",
            "bytes": len(payload),
            "mode": oct(path.stat().st_mode & 0o777),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    module.build_deterministic_overlay_tar(repository, records, first)
    module.build_deterministic_overlay_tar(repository, records, second)
    module.verify_deterministic_overlay_tar(first, records)
    assert first.read_bytes() == second.read_bytes()

    patch = tmp_path / "change.patch"
    patch.write_bytes(_run(repository, "diff", "--binary", "HEAD"))
    patch_tree = tmp_path / "patch-tree"
    tar_tree = tmp_path / "tar-tree"
    _run(tmp_path, "clone", "--quiet", str(repository), str(patch_tree))
    _run(tmp_path, "clone", "--quiet", str(repository), str(tar_tree))
    _run(patch_tree, "apply", str(patch))
    with tarfile.open(first, "r:gz") as archive:
        for member in archive.getmembers():
            target = tar_tree / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            assert stream is not None
            target.write_bytes(stream.read())
            os.chmod(target, member.mode)
    _run(patch_tree, "add", "-A")
    _run(tar_tree, "add", "-A")
    assert _run(patch_tree, "write-tree") == _run(tar_tree, "write-tree")
