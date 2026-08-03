from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Callable

import pytest


REPOSITORY_ROOT = Path(__file__).parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "tools" / "ac23"
sys.path.insert(0, os.fspath(TOOLS_ROOT))

from archive_safety import (  # noqa: E402
    ArchiveLimits,
    ArchiveSafetyError,
    inspect_tar,
)
from verify_candidate_artifact_identity import (  # noqa: E402
    APPROVED_BASE_COMMIT,
    APPROVED_BASE_TREE,
    APPROVED_REPOSITORY_URL,
    MANIFEST_KEYS,
    NORMATIVE_CONTRACT_PATH,
    NORMATIVE_CONTRACT_SHA256,
    normalize_repository_url,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_bytes(path: Path, payload: bytes) -> None:
    replacement = path.with_name(path.name + ".replacement")
    replacement.write_bytes(payload)
    os.replace(replacement, path)


def _manifest(package: Path) -> dict[str, str]:
    return json.loads(
        (package / "IDENTITY" / "candidate_artifact_identity.json").read_text(
            encoding="utf-8"
        )
    )


def _write_manifest(package: Path, manifest: dict[str, str]) -> None:
    payload = (
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    _replace_bytes(
        package / "IDENTITY" / "candidate_artifact_identity.json", payload
    )


def _run_verifier(package: Path) -> tuple[int, str, str]:
    verifier = package / "VERIFY" / "verify_candidate_artifact_identity.py"
    completed = subprocess.run(
        [sys.executable, os.fspath(verifier), os.fspath(package)],
        cwd=package,
        env={
            "PATH": os.environ.get("PATH", ""),
            "LC_ALL": "C",
            "TZ": "UTC",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    code = ""
    for line in completed.stderr.splitlines():
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            code = str(parsed.get("error_code", ""))
    return completed.returncode, code, completed.stdout


def _copy_package(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination, copy_function=os.link)
    return destination


def _flip_byte(path: Path) -> None:
    payload = bytearray(path.read_bytes())
    assert payload
    offset = len(payload) // 2
    payload[offset] ^= 1
    _replace_bytes(path, bytes(payload))


def _mutate_hex(value: str) -> str:
    return ("0" if value[0] != "0" else "1") + value[1:]


def _rewrite_tar(
    path: Path,
    transform: Callable[[tarfile.TarInfo, bytes | None], tuple[tarfile.TarInfo, bytes | None]],
    additions: list[tuple[tarfile.TarInfo, bytes | None]] | None = None,
) -> None:
    replacement = path.with_name(path.name + ".replacement")
    with tarfile.open(path, "r:*", encoding="utf-8", errors="surrogateescape") as source:
        original: list[tuple[tarfile.TarInfo, bytes | None]] = []
        for member in source.getmembers():
            payload = None
            if member.isfile():
                extracted = source.extractfile(member)
                assert extracted is not None
                payload = extracted.read()
            original.append((member, payload))
    with tarfile.open(
        replacement,
        "w",
        format=tarfile.PAX_FORMAT,
        encoding="utf-8",
        errors="surrogateescape",
    ) as target:
        for member, payload in original:
            changed, changed_payload = transform(member, payload)
            target.addfile(
                changed,
                io.BytesIO(changed_payload) if changed_payload is not None else None,
            )
        for member, payload in additions or []:
            target.addfile(member, io.BytesIO(payload) if payload is not None else None)
    os.replace(replacement, path)


def _new_tar_info(
    name: str,
    payload: bytes = b"x",
    *,
    mode: int = 0o644,
    type_: bytes = tarfile.REGTYPE,
    linkname: str = "",
) -> tuple[tarfile.TarInfo, bytes | None]:
    member = tarfile.TarInfo(name)
    member.type = type_
    member.mode = mode
    member.uid = member.gid = member.mtime = 0
    member.uname = member.gname = ""
    member.linkname = linkname
    if type_ == tarfile.REGTYPE:
        member.size = len(payload)
        return member, payload
    member.size = 0
    return member, None


@pytest.fixture(scope="session")
def package_root() -> Path:
    value = os.environ.get("AC23_PACKAGE_ROOT")
    if not value:
        pytest.skip("AC23_PACKAGE_ROOT is required for package acceptance tests")
    root = Path(value).resolve()
    assert root.is_dir()
    return root


@pytest.fixture(scope="session")
def manifest(package_root: Path) -> dict[str, str]:
    return _manifest(package_root)


@pytest.fixture(scope="session")
def valid_verification(package_root: Path) -> None:
    exit_code, error_code, stdout = _run_verifier(package_root)
    assert exit_code == 0
    assert error_code == ""
    assert stdout.splitlines()[-1] == "AC23_PASS=YES"


@pytest.fixture(scope="session")
def bundle_repository(package_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    repository = tmp_path_factory.mktemp("bundle")
    bundle = package_root / "SOURCE" / "candidate_repository.bundle"
    subprocess.run(["git", "init", "--bare", "--quiet"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "fetch",
            "--no-tags",
            os.fspath(bundle),
            "refs/heads/candidate:refs/ac23/candidate",
        ],
        cwd=repository,
        env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "TZ": "UTC"},
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return repository


def _git_output(repository: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=repository,
        env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "TZ": "UTC"},
        text=True,
    ).strip()


# The following sixteen tests map one-for-one to the directive's normal matrix.
def test_normal_01_bundle_contains_head(valid_verification: None, manifest: dict[str, str], bundle_repository: Path) -> None:
    assert _git_output(bundle_repository, "cat-file", "-t", manifest["head_commit"]) == "commit"


def test_normal_02_head_tree(valid_verification: None, manifest: dict[str, str], bundle_repository: Path) -> None:
    assert _git_output(bundle_repository, "show", "-s", "--format=%T", manifest["head_commit"]) == manifest["head_tree"]


def test_normal_03_base_tree(valid_verification: None, manifest: dict[str, str], bundle_repository: Path) -> None:
    assert manifest["base_commit"] == APPROVED_BASE_COMMIT
    assert _git_output(bundle_repository, "show", "-s", "--format=%T", manifest["base_commit"]) == APPROVED_BASE_TREE


def test_normal_04_ancestry(valid_verification: None, manifest: dict[str, str], bundle_repository: Path) -> None:
    result = subprocess.run(["git", "merge-base", "--is-ancestor", manifest["base_commit"], manifest["head_commit"]], cwd=bundle_repository, check=False)
    assert result.returncode == 0


def test_normal_05_patch_digest(valid_verification: None, package_root: Path, manifest: dict[str, str]) -> None:
    assert _sha256(package_root / "PATCH" / "cumulative.patch") == manifest["patch_sha256"]


def test_normal_06_patch_tree(valid_verification: None, manifest: dict[str, str]) -> None:
    assert manifest["patch_applied_tree"] == manifest["head_tree"]


def test_normal_07_source_digest(valid_verification: None, package_root: Path, manifest: dict[str, str]) -> None:
    assert _sha256(package_root / "SOURCE" / "candidate_source.tar") == manifest["source_archive_sha256"]


def test_normal_08_source_tree(valid_verification: None, manifest: dict[str, str]) -> None:
    assert manifest["source_archive_tree"] == manifest["head_tree"]


def test_normal_09_submitted_head(valid_verification: None, manifest: dict[str, str]) -> None:
    assert manifest["submitted_head_tree"] == manifest["head_tree"]


def test_normal_10_all_trees_equal(valid_verification: None, manifest: dict[str, str]) -> None:
    assert len({manifest[key] for key in ("head_tree", "submitted_head_tree", "patch_applied_tree", "source_archive_tree")}) == 1


def test_normal_11_changed_paths(valid_verification: None, package_root: Path, manifest: dict[str, str]) -> None:
    changed = (package_root / "IDENTITY" / "changed_paths.nul").read_bytes()
    assert _sha256(package_root / "IDENTITY" / "changed_paths.nul") == manifest["changed_path_manifest_sha256"]
    paths = changed[:-1].split(b"\0") if changed else []
    assert paths == sorted(paths)


def test_normal_12_evidence_digest(valid_verification: None, package_root: Path, manifest: dict[str, str]) -> None:
    assert _sha256(package_root / "EVIDENCE" / "evidence_raw.tar") == manifest["evidence_sha256"]


def test_normal_13_contract_digest(valid_verification: None, manifest: dict[str, str], bundle_repository: Path) -> None:
    payload = subprocess.check_output(["git", "show", f"{manifest['head_commit']}:{NORMATIVE_CONTRACT_PATH}"], cwd=bundle_repository)
    assert hashlib.sha256(payload).hexdigest() == NORMATIVE_CONTRACT_SHA256


def test_normal_14_repository_url(valid_verification: None, manifest: dict[str, str]) -> None:
    assert manifest["repository_url"] == APPROVED_REPOSITORY_URL
    assert normalize_repository_url(manifest["repository_url"]) == APPROVED_REPOSITORY_URL


def test_normal_15_clean_inventory(valid_verification: None, package_root: Path) -> None:
    with tarfile.open(package_root / "EVIDENCE" / "evidence_raw.tar", "r:") as archive:
        clean = archive.extractfile("clean_status.bin")
        assert clean is not None and clean.read() == b""


def test_normal_16_frozen_regression(valid_verification: None, package_root: Path) -> None:
    with tarfile.open(package_root / "EVIDENCE" / "evidence_raw.tar", "r:") as archive:
        source = archive.extractfile("regression/frozen_19_summary.json")
        assert source is not None
        summary = json.load(source)
    assert summary == {"failed": 0, "passed": 19, "total": 19}


def _mutation_package(package_root: Path, tmp_path: Path) -> Path:
    return _copy_package(package_root, tmp_path / "package")


def _expect_failure(package: Path, accepted: set[str]) -> None:
    exit_code, error_code, _ = _run_verifier(package)
    assert exit_code != 0
    assert error_code in accepted


def test_mutation_01_head_commit(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    value = _manifest(package)
    value["head_commit"] = _mutate_hex(value["head_commit"])
    _write_manifest(package, value)
    _expect_failure(package, {"E_HEAD_OBJECT", "E_HEAD_TREE"})


def test_mutation_02_head_tree(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    value = _manifest(package)
    value["head_tree"] = _mutate_hex(value["head_tree"])
    _write_manifest(package, value)
    _expect_failure(package, {"E_HEAD_TREE"})


def test_mutation_03_base_commit(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    value = _manifest(package)
    value["base_commit"] = _mutate_hex(value["base_commit"])
    _write_manifest(package, value)
    _expect_failure(package, {"E_BASE_OBJECT"})


def test_mutation_04_base_tree(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    value = _manifest(package)
    value["base_tree"] = _mutate_hex(value["base_tree"])
    _write_manifest(package, value)
    _expect_failure(package, {"E_BASE_TREE"})


def test_mutation_05_repository_url(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    value = _manifest(package)
    value["repository_url"] = "https://example.invalid/repository.git"
    _write_manifest(package, value)
    _expect_failure(package, {"E_REPOSITORY_URL"})


@pytest.mark.parametrize(
    ("relative", "error"),
    [
        ("PATCH/cumulative.patch", "E_PATCH_DIGEST"),
        ("SOURCE/candidate_source.tar", "E_SOURCE_DIGEST"),
        ("IDENTITY/changed_paths.nul", "E_CHANGED_PATH_DIGEST"),
        ("EVIDENCE/evidence_raw.tar", "E_EVIDENCE_DIGEST"),
    ],
)
def test_mutation_06_to_09_raw_digest(
    package_root: Path, tmp_path: Path, relative: str, error: str
) -> None:
    package = _mutation_package(package_root, tmp_path)
    _flip_byte(package / relative)
    _expect_failure(package, {error})


def test_mutation_10_contract_digest(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    value = _manifest(package)
    value["normative_contract_sha256"] = "0" * 64
    _write_manifest(package, value)
    _expect_failure(package, {"E_CONTRACT_DIGEST"})


def test_mutation_11_bundle(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    _replace_bytes(package / "SOURCE" / "candidate_repository.bundle", b"not-a-bundle\n")
    _expect_failure(package, {"E_BUNDLE", "E_HEAD_OBJECT"})


def test_mutation_12_resealed_patch_tree(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    path = package / "PATCH" / "cumulative.patch"
    lines = path.read_bytes().splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(b"+") and not line.startswith(b"+++") and len(line.rstrip()) > 2:
            body = bytearray(line)
            offset = len(body.rstrip()) - 1
            body[offset] = ord("X") if body[offset] != ord("X") else ord("Y")
            lines[index] = bytes(body)
            break
    else:
        pytest.fail("no mutable patch addition")
    _replace_bytes(path, b"".join(lines))
    value = _manifest(package)
    value["patch_sha256"] = _sha256(path)
    _write_manifest(package, value)
    _expect_failure(package, {"E_PATCH_TREE"})


def test_mutation_13_resealed_source_tree(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    path = package / "SOURCE" / "candidate_source.tar"
    changed = False

    def transform(member: tarfile.TarInfo, payload: bytes | None) -> tuple[tarfile.TarInfo, bytes | None]:
        nonlocal changed
        if not changed and member.isfile() and payload:
            payload = bytes([payload[0] ^ 1]) + payload[1:]
            member.size = len(payload)
            changed = True
        return member, payload

    _rewrite_tar(path, transform)
    assert changed
    value = _manifest(package)
    value["source_archive_sha256"] = _sha256(path)
    _write_manifest(package, value)
    _expect_failure(package, {"E_SOURCE_TREE"})


def test_mutation_14_source_mode(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    path = package / "SOURCE" / "candidate_source.tar"
    changed = False

    def transform(member: tarfile.TarInfo, payload: bytes | None) -> tuple[tarfile.TarInfo, bytes | None]:
        nonlocal changed
        if not changed and member.isfile() and not (member.mode & 0o111):
            member.mode |= 0o111
            changed = True
        return member, payload

    _rewrite_tar(path, transform)
    assert changed
    value = _manifest(package)
    value["source_archive_sha256"] = _sha256(path)
    _write_manifest(package, value)
    _expect_failure(package, {"E_SOURCE_TREE"})


def test_mutation_15_source_untracked(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    path = package / "SOURCE" / "candidate_source.tar"
    _rewrite_tar(path, lambda member, payload: (member, payload), [_new_tar_info("candidate/ac23-untracked.txt")])
    value = _manifest(package)
    value["source_archive_sha256"] = _sha256(path)
    _write_manifest(package, value)
    _expect_failure(package, {"E_SOURCE_TREE"})


@pytest.mark.parametrize(
    "addition",
    [
        _new_tar_info("candidate/../escape.txt"),
        _new_tar_info("/absolute.txt"),
        _new_tar_info(
            "candidate/escape-link",
            b"",
            type_=tarfile.SYMTYPE,
            linkname="../../outside",
        ),
    ],
)
def test_mutation_16_archive_escape(
    package_root: Path,
    tmp_path: Path,
    addition: tuple[tarfile.TarInfo, bytes | None],
) -> None:
    package = _mutation_package(package_root, tmp_path)
    path = package / "SOURCE" / "candidate_source.tar"
    _rewrite_tar(path, lambda member, payload: (member, payload), [addition])
    value = _manifest(package)
    value["source_archive_sha256"] = _sha256(path)
    _write_manifest(package, value)
    _expect_failure(package, {"E_ARCHIVE_SAFETY"})


@pytest.mark.parametrize(
    "additions",
    [
        [_new_tar_info("candidate/collision.txt"), _new_tar_info("candidate/collision.txt")],
        [_new_tar_info("candidate/Case.txt"), _new_tar_info("candidate/case.txt")],
        [_new_tar_info("candidate/\u00e9.txt"), _new_tar_info("candidate/e\u0301.txt")],
    ],
)
def test_mutation_17_archive_collision(
    package_root: Path,
    tmp_path: Path,
    additions: list[tuple[tarfile.TarInfo, bytes | None]],
) -> None:
    package = _mutation_package(package_root, tmp_path)
    path = package / "SOURCE" / "candidate_source.tar"
    _rewrite_tar(path, lambda member, payload: (member, payload), additions)
    value = _manifest(package)
    value["source_archive_sha256"] = _sha256(path)
    _write_manifest(package, value)
    _expect_failure(package, {"E_ARCHIVE_SAFETY"})


def test_mutation_18_self_reference(package_root: Path, tmp_path: Path) -> None:
    package = _mutation_package(package_root, tmp_path)
    path = package / "SOURCE" / "candidate_source.tar"
    payload = (package / "IDENTITY" / "candidate_artifact_identity.json").read_bytes()
    _rewrite_tar(
        path,
        lambda member, content: (member, content),
        [_new_tar_info("candidate/candidate_artifact_identity.json", payload)],
    )
    value = _manifest(package)
    value["source_archive_sha256"] = _sha256(path)
    _write_manifest(package, value)
    _expect_failure(package, {"E_SELF_REFERENCE", "E_SOURCE_TREE"})


@pytest.mark.parametrize("variant", ["missing", "unknown", "duplicate"])
def test_mutation_19_schema(package_root: Path, tmp_path: Path, variant: str) -> None:
    package = _mutation_package(package_root, tmp_path)
    path = package / "IDENTITY" / "candidate_artifact_identity.json"
    value = _manifest(package)
    if variant == "missing":
        value.pop("head_tree")
        _write_manifest(package, value)
    elif variant == "unknown":
        value["unknown"] = "forbidden"
        _write_manifest(package, value)
    else:
        payload = path.read_text(encoding="utf-8").rstrip()
        assert payload.endswith("}")
        _replace_bytes(path, (payload[:-1] + ',"head_tree":"' + value["head_tree"] + '"}\n').encode("utf-8"))
    _expect_failure(package, {"E_SCHEMA"})


@pytest.mark.parametrize("variant", ["reordered", "missing"])
def test_mutation_20_changed_path_semantics(package_root: Path, tmp_path: Path, variant: str) -> None:
    package = _mutation_package(package_root, tmp_path)
    path = package / "IDENTITY" / "changed_paths.nul"
    payload = path.read_bytes()
    entries = payload[:-1].split(b"\0") if payload else []
    assert len(entries) >= 2
    changed = list(reversed(entries)) if variant == "reordered" else entries[:-1]
    _replace_bytes(path, b"".join(item + b"\0" for item in changed))
    value = _manifest(package)
    value["changed_path_manifest_sha256"] = _sha256(path)
    _write_manifest(package, value)
    _expect_failure(package, {"E_CHANGED_PATH_DIGEST"})


# Fast source-level tests run before the candidate commit exists.
def test_unit_url_scp_normalization() -> None:
    assert normalize_repository_url("git@GitHub.com:Owner/Repo.git/") == "ssh://git@github.com/Owner/Repo.git"


@pytest.mark.parametrize(
    "value",
    [
        "https://user:password@example.com/repo.git",
        "https://example.com/repo.git?token=x",
        "https://example.com/repo.git#fragment",
    ],
)
def test_unit_url_rejects_credential_material(value: str) -> None:
    with pytest.raises(Exception):
        normalize_repository_url(value)


def test_unit_archive_limits_cannot_be_raised(tmp_path: Path) -> None:
    archive = tmp_path / "empty.tar"
    with tarfile.open(archive, "w"):
        pass
    with pytest.raises(ArchiveSafetyError):
        inspect_tar(
            archive,
            allowed_roots={"candidate"},
            limits=ArchiveLimits(max_members=100_001),
        )


def test_unit_manifest_key_set_is_exact() -> None:
    assert len(MANIFEST_KEYS) == 17
    assert "head_commit" in MANIFEST_KEYS
    assert "evidence_sha256" in MANIFEST_KEYS
