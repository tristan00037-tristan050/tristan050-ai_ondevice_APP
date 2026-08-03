#!/usr/bin/env python3
"""Build a deterministic, independently verifiable Butler AC-23 package."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from archive_safety import ArchiveSafetyError, safe_extract_tar
from verify_candidate_artifact_identity import (
    APPROVED_BASE_COMMIT,
    APPROVED_BASE_TREE,
    APPROVED_REPOSITORY_URL,
    NORMATIVE_CONTRACT_PATH,
    NORMATIVE_CONTRACT_SHA256,
    load_evidence_policy,
    normalize_repository_url,
    verify_evidence_semantics,
)


SCHEMA_VERSION = "butler.box5.candidate-artifact-identity.v1"
ROUND5_START_COMMIT = "fbb90e182063edc50651d769cac9e840cf96ac3e"
ROUND5_START_TREE = "c94833ca4ff2ff57cddccb48bd289305eaf33f94"
ALLOWED_AC23_PATH_PREFIXES = ("tools/ac23/", "tests/ac23/")
ALLOWED_AC23_PATHS = {"schemas/candidate-artifact-identity-v1.schema.json"}
ALLOWED_REQUIRED_METADATA_PATHS = {
    "integration_lock.json",
    "scripts/verify_box5_integration_lock.py",
}


class BuildError(RuntimeError):
    pass


def _git_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "SYSTEMROOT", "TMPDIR"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    if extra:
        env.update(extra)
    return env


def _git(
    cwd: Path,
    *args: str | os.PathLike[str],
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    argv = [
        "git",
        "-c",
        "core.autocrlf=false",
        "-c",
        "core.safecrlf=false",
        "-c",
        "core.filemode=true",
        "-c",
        "core.symlinks=true",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        f"core.excludesFile={os.devnull}",
        *(os.fspath(arg) for arg in args),
    ]
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=_git_env(),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise BuildError(f"Git command failed with exit {result.returncode}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
    os.chmod(path, mode)


def _tar_info(name: str, *, mode: int, size: int = 0) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.mode = mode
    info.size = size
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.pax_headers = {}
    return info


def _parse_tree(repository: Path, head: str) -> list[tuple[bytes, bytes, bytes]]:
    output = _git(
        repository, "ls-tree", "-r", "-z", "--full-tree", head
    ).stdout
    entries: list[tuple[bytes, bytes, bytes]] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or len(fields) != 3 or not path:
            raise BuildError("invalid Git tree record")
        mode, object_type, oid = fields
        if object_type != b"blob" or mode not in {b"100644", b"100755", b"120000"}:
            raise BuildError("gitlinks and unsupported tree modes are forbidden")
        if path.startswith(b"/") or b"\\" in path:
            raise BuildError("unsafe Git tree path")
        parts = path.split(b"/")
        if any(part in {b"", b".", b".."} for part in parts):
            raise BuildError("unsafe Git tree path")
        entries.append((path, mode, oid))
    entries.sort(key=lambda item: item[0])
    return entries


def _build_source_tar(repository: Path, head: str, destination: Path) -> None:
    entries = _parse_tree(repository, head)
    directories: set[bytes] = {b"candidate"}
    for path, _, _ in entries:
        parts = path.split(b"/")
        for depth in range(1, len(parts)):
            directories.add(b"candidate/" + b"/".join(parts[:depth]))
    with tarfile.open(
        destination,
        "x",
        format=tarfile.PAX_FORMAT,
        encoding="utf-8",
        errors="surrogateescape",
    ) as archive:
        for directory in sorted(directories):
            name = directory.decode("utf-8", "surrogateescape") + "/"
            info = _tar_info(name, mode=0o755)
            info.type = tarfile.DIRTYPE
            archive.addfile(info)
        for path, mode, oid in entries:
            payload = _git(repository, "cat-file", "blob", oid.decode("ascii")).stdout
            name = "candidate/" + path.decode("utf-8", "surrogateescape")
            if mode == b"120000":
                info = _tar_info(name, mode=0o777)
                info.type = tarfile.SYMTYPE
                info.linkname = payload.decode("utf-8", "surrogateescape")
                archive.addfile(info)
            else:
                info = _tar_info(
                    name,
                    mode=0o755 if mode == b"100755" else 0o644,
                    size=len(payload),
                )
                archive.addfile(info, io.BytesIO(payload))


def _safe_evidence_paths(root: Path) -> tuple[list[Path], list[Path]]:
    required_files = {
        "environment.json",
        "commands.jsonl",
        "clean_status.bin",
        "tree_reconstruction.json",
        "regression/frozen_19_details.json",
        "regression/frozen_19_summary.json",
        "mutation/mutation_results_v2.json",
        "mutation/pytest_mutation.stdout.bin",
        "mutation/pytest_mutation.stderr.bin",
        "mutation/pytest_mutation.xml",
    }
    required_directories = {"regression", "mutation", "stdout", "stderr"}
    actual_files: list[Path] = []
    actual_directories: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        parts = relative.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise BuildError("unsafe evidence path")
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise BuildError("evidence must contain only directories and regular files")
        if path.is_dir():
            actual_directories.append(path)
        else:
            actual_files.append(path)
    file_names = {path.relative_to(root).as_posix() for path in actual_files}
    directory_names = {path.relative_to(root).as_posix() for path in actual_directories}
    if not required_files.issubset(file_names) or not required_directories.issubset(
        directory_names
    ):
        raise BuildError("evidence inventory is incomplete")
    return actual_directories, actual_files


def _build_evidence_tar(evidence_root: Path, destination: Path) -> None:
    directories, files = _safe_evidence_paths(evidence_root)
    with tarfile.open(destination, "x", format=tarfile.PAX_FORMAT) as archive:
        for directory in sorted(directories, key=lambda path: path.relative_to(evidence_root).as_posix()):
            name = directory.relative_to(evidence_root).as_posix() + "/"
            info = _tar_info(name, mode=0o755)
            info.type = tarfile.DIRTYPE
            archive.addfile(info)
        for source in sorted(files, key=lambda path: path.relative_to(evidence_root).as_posix()):
            payload = source.read_bytes()
            name = source.relative_to(evidence_root).as_posix()
            info = _tar_info(name, mode=0o644, size=len(payload))
            archive.addfile(info, io.BytesIO(payload))


def _changed_paths(repository: Path, base: str, head: str) -> bytes:
    output = _git(
        repository,
        "diff",
        "--name-only",
        "-z",
        "--no-renames",
        base,
        head,
        "--",
    ).stdout
    if output and not output.endswith(b"\0"):
        raise BuildError("changed path output is not NUL terminated")
    paths = output[:-1].split(b"\0") if output else []
    if len(paths) != len(set(paths)):
        raise BuildError("duplicate changed path")
    return b"".join(path + b"\0" for path in sorted(paths))


def _create_bundle(repository: Path, head: str, destination: Path, temporary: Path) -> None:
    bare = temporary / "bundle-source.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "--quiet")
    _git(
        bare,
        "fetch",
        "--no-tags",
        repository,
        f"{head}:refs/heads/candidate",
    )
    _git(bare, "bundle", "create", destination, "refs/heads/candidate")
    verified = _git(bare, "bundle", "verify", destination)
    text = (verified.stdout + verified.stderr).decode("utf-8", "replace").lower()
    if "complete history" not in text:
        raise BuildError("candidate bundle is not self-contained")


def _patch_tree(bundle: Path, patch: Path, base: str, temporary: Path) -> str:
    repository = temporary / "patch-tree"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(
        repository,
        "fetch",
        "--no-tags",
        bundle,
        "refs/heads/candidate:refs/ac23/candidate",
    )
    _git(repository, "checkout", "--detach", "--force", base)
    if _git(repository, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout:
        raise BuildError("base checkout is dirty")
    if _git(repository, "apply", "--check", "--binary", patch, check=False).returncode:
        raise BuildError("cumulative patch does not apply")
    if _git(repository, "apply", "--binary", "--index", patch, check=False).returncode:
        raise BuildError("cumulative patch application failed")
    if _git(repository, "diff", "--cached", "--check", check=False).returncode:
        raise BuildError("cumulative patch introduces whitespace errors")
    return _git(repository, "write-tree").stdout.decode("ascii").strip()


def _source_tree(source_tar: Path, temporary: Path) -> str:
    extracted = temporary / "source-extracted"
    try:
        safe_extract_tar(source_tar, extracted, allowed_roots={"candidate"})
    except ArchiveSafetyError as error:
        raise BuildError("candidate source archive is unsafe") from error
    repository = extracted / "candidate"
    _git(repository, "init", "--quiet")
    _git(repository, "add", "-f", "-A")
    return _git(repository, "write-tree").stdout.decode("ascii").strip()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _readme(manifest: dict[str, str]) -> bytes:
    return (
        "# Butler Box5 AC-23 독립 검증 꾸러미\n\n"
        "이 디렉터리는 네트워크와 원 개발 작업공간 없이 검증됩니다.\n\n"
        "```bash\npython3 VERIFY/verify_candidate_artifact_identity.py .\n```\n\n"
        "정상 판정의 마지막 줄은 `AC23_PASS=YES`입니다.\n\n"
        f"- repository_url: `{manifest['repository_url']}`\n"
        f"- base_commit: `{manifest['base_commit']}`\n"
        f"- head_commit: `{manifest['head_commit']}`\n"
        f"- head_tree: `{manifest['head_tree']}`\n"
    ).encode("utf-8")


def _validate_candidate(
    repository: Path,
    base: str,
    head: str,
) -> tuple[str, str, str]:
    if _git(repository, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout:
        raise BuildError("candidate worktree is not clean")
    actual_head = _git(repository, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode(
        "ascii"
    ).strip()
    if actual_head != head:
        raise BuildError("requested head is not the checked out clean candidate")
    if _git(repository, "cat-file", "-t", base).stdout.strip() != b"commit":
        raise BuildError("approved base is not a commit")
    base_tree = _git(repository, "show", "-s", "--format=%T", base).stdout.decode(
        "ascii"
    ).strip()
    if base != APPROVED_BASE_COMMIT or base_tree != APPROVED_BASE_TREE:
        raise BuildError("approved base identity mismatch")
    if _git(repository, "merge-base", "--is-ancestor", base, head, check=False).returncode:
        raise BuildError("approved base is not an ancestor of candidate")
    head_tree = _git(repository, "show", "-s", "--format=%T", head).stdout.decode(
        "ascii"
    ).strip()
    object_format = _git(repository, "rev-parse", "--show-object-format").stdout.decode(
        "ascii"
    ).strip()
    if object_format != "sha1":
        raise BuildError("unsupported Git object format")
    if _git(repository, "show", "-s", "--format=%T", ROUND5_START_COMMIT).stdout.decode("ascii").strip() != ROUND5_START_TREE:
        raise BuildError("Round5 start identity mismatch")
    if _git(repository, "merge-base", "--is-ancestor", ROUND5_START_COMMIT, head, check=False).returncode:
        raise BuildError("Round5 start is not an ancestor")
    delta = _git(
        repository,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-z",
        ROUND5_START_COMMIT,
        head,
    ).stdout
    for raw_path in delta.split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", "surrogateescape")
        if (
            path not in ALLOWED_AC23_PATHS
            and path not in ALLOWED_REQUIRED_METADATA_PATHS
            and not path.startswith(ALLOWED_AC23_PATH_PREFIXES)
        ):
            raise BuildError("product-code freeze violation")
    return base_tree, head_tree, object_format


def build(args: argparse.Namespace) -> Path:
    repository = args.repo.resolve()
    output = args.output.resolve()
    evidence = args.evidence_dir.resolve()
    verifier_source = args.verifier_source.resolve()
    schema_source = args.schema_source.resolve()
    policy_source = args.policy_source.resolve()
    policy_bytes = policy_source.read_bytes()
    policy = load_evidence_policy(policy_bytes)
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise BuildError("output directory must be absent or empty")
        output.rmdir()
    repository_url = normalize_repository_url(args.repository_url)
    if repository_url != APPROVED_REPOSITORY_URL:
        raise BuildError("repository URL is not the approved canonical URL")

    head = _git(repository, "rev-parse", "--verify", f"{args.head_commit}^{{commit}}").stdout.decode(
        "ascii"
    ).strip()
    base_tree, head_tree, object_format = _validate_candidate(
        repository, args.base_commit, head
    )
    contract = _git(repository, "show", f"{head}:{NORMATIVE_CONTRACT_PATH}").stdout
    contract_digest = hashlib.sha256(contract).hexdigest()
    if contract_digest != NORMATIVE_CONTRACT_SHA256:
        raise BuildError("normative contract digest mismatch")

    output_parent = output.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=".ac23-build-", dir=output_parent))
    staging = temporary_root / "AC23_FINAL"
    staging.mkdir()
    try:
        for relative in ("IDENTITY", "PATCH", "SOURCE", "EVIDENCE", "VERIFY"):
            (staging / relative).mkdir()
        patch_path = staging / "PATCH" / "cumulative.patch"
        patch = _git(
            repository,
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-renames",
            args.base_commit,
            head,
            "--",
        ).stdout
        _write_bytes(patch_path, patch)
        changed_path = staging / "IDENTITY" / "changed_paths.nul"
        _write_bytes(changed_path, _changed_paths(repository, args.base_commit, head))
        source_path = staging / "SOURCE" / "candidate_source.tar"
        _build_source_tar(repository, head, source_path)
        bundle_path = staging / "SOURCE" / "candidate_repository.bundle"
        _create_bundle(repository, head, bundle_path, temporary_root)
        evidence_path = staging / "EVIDENCE" / "evidence_raw.tar"
        _build_evidence_tar(evidence, evidence_path)

        patch_tree = _patch_tree(bundle_path, patch_path, args.base_commit, temporary_root)
        source_tree = _source_tree(source_path, temporary_root)
        if patch_tree != head_tree or source_tree != head_tree:
            raise BuildError("independently reconstructed trees do not match candidate")

        manifest: dict[str, str] = {
            "schema_version": SCHEMA_VERSION,
            "digest_algorithm": "sha256",
            "repository_url": repository_url,
            "object_format": object_format,
            "base_commit": args.base_commit,
            "base_tree": base_tree,
            "head_commit": head,
            "head_tree": head_tree,
            "submitted_head_tree": head_tree,
            "patch_applied_tree": patch_tree,
            "source_archive_tree": source_tree,
            "patch_sha256": _sha256(patch_path),
            "source_archive_sha256": _sha256(source_path),
            "changed_path_manifest_sha256": _sha256(changed_path),
            "evidence_sha256": _sha256(evidence_path),
            "normative_contract_path": NORMATIVE_CONTRACT_PATH,
            "normative_contract_sha256": contract_digest,
        }
        verify_evidence_semantics(evidence_path, manifest, policy)
        _write_bytes(
            staging / "IDENTITY" / "candidate_artifact_identity.json",
            _canonical_json(manifest),
        )
        shutil.copyfile(verifier_source, staging / "VERIFY" / verifier_source.name)
        os.chmod(staging / "VERIFY" / verifier_source.name, 0o755)
        shutil.copyfile(schema_source, staging / "VERIFY" / schema_source.name)
        os.chmod(staging / "VERIFY" / schema_source.name, 0o644)
        shutil.copyfile(policy_source, staging / "VERIFY" / policy_source.name)
        os.chmod(staging / "VERIFY" / policy_source.name, 0o644)
        _write_bytes(staging / "README_KO.md", _readme(manifest))

        files = sorted(
            path
            for path in staging.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS.txt"
        )
        checksum_lines = "".join(
            f"{_sha256(path)}  {path.relative_to(staging).as_posix()}\n" for path in files
        ).encode("utf-8")
        _write_bytes(staging / "SHA256SUMS.txt", checksum_lines)
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    else:
        shutil.rmtree(temporary_root, ignore_errors=True)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Butler AC-23 identity package")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--repository-url", default=APPROVED_REPOSITORY_URL)
    parser.add_argument("--base-commit", default=APPROVED_BASE_COMMIT)
    parser.add_argument("--head-commit", default="HEAD")
    parser.add_argument(
        "--verifier-source",
        type=Path,
        default=Path(__file__).with_name("verify_candidate_artifact_identity.py"),
    )
    parser.add_argument(
        "--schema-source",
        type=Path,
        default=Path(__file__).parents[2]
        / "schemas"
        / "candidate-artifact-identity-v1.schema.json",
    )
    parser.add_argument(
        "--policy-source",
        type=Path,
        default=Path(__file__).with_name("evidence_policy_v2.json"),
    )
    return parser


def main() -> int:
    try:
        output = build(_parser().parse_args())
    except Exception:
        print(
            json.dumps(
                {"ac23_build": 0, "error_code": "E_BUILD"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print('{"ac23_build":1,"error_code":""}')
    print(f"AC23_PACKAGE={output}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
