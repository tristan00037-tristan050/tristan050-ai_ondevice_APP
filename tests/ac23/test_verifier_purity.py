from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


TOOLS_ROOT = Path(__file__).parents[2] / "tools" / "ac23"
sys.path.insert(0, os.fspath(TOOLS_ROOT))

import verify_candidate_artifact_identity as verifier  # noqa: E402


def _source_package() -> Path:
    value = os.environ.get("AC23_PACKAGE_ROOT")
    if not value:
        pytest.skip("AC23_PACKAGE_ROOT is required")
    return Path(value).resolve()


def _snapshot(root: Path) -> tuple[tuple[object, ...], ...]:
    rows: list[tuple[object, ...]] = []
    for path in [root, *sorted(root.rglob("*"))]:
        relative = "." if path == root else path.relative_to(root).as_posix()
        status = path.lstat()
        if path.is_dir():
            rows.append(("d", relative, status.st_mode & 0o7777))
        else:
            rows.append(
                (
                    "f",
                    relative,
                    status.st_mode & 0o7777,
                    status.st_size,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
    return tuple(rows)


def _run(package: Path, cwd: Path, work_root: Path | None = None) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, os.fspath(package / "VERIFY/verify_candidate_artifact_identity.py"), os.fspath(package)]
    if work_root is not None:
        argv.extend(["--work-root", os.fspath(work_root)])
    return subprocess.run(
        argv,
        cwd=cwd,
        env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "TZ": "UTC"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _error_code(completed: subprocess.CompletedProcess[str]) -> str:
    for line in completed.stderr.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if type(value) is dict and type(value.get("error_code")) is str:
            return value["error_code"]
    return ""


def _copy(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    shutil.copytree(_source_package(), package, copy_function=shutil.copy2)
    return package


def test_evidence_semantics_attack_verifier_purity_no_tmp_and_repeatable(tmp_path: Path) -> None:
    package = _copy(tmp_path)
    before = _snapshot(package)
    first = _run(package, tmp_path)
    middle = _snapshot(package)
    second = _run(package, tmp_path)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert before == middle == _snapshot(package)
    assert not list(tmp_path.glob(".ac23-verify-*"))


def test_evidence_semantics_attack_verifier_purity_read_only_input(tmp_path: Path) -> None:
    package = _copy(tmp_path)
    paths = [package, *package.rglob("*")]
    original_modes = {path: path.lstat().st_mode & 0o7777 for path in paths}
    try:
        for path in sorted(paths, key=lambda item: len(item.parts), reverse=True):
            path.chmod(0o555 if path.is_dir() else 0o444)
        before = _snapshot(package)
        completed = _run(package, tmp_path)
        assert completed.returncode == 0
        assert _snapshot(package) == before
    finally:
        for path in sorted(paths, key=lambda item: len(item.parts)):
            if path.exists():
                path.chmod(original_modes[path])


def test_evidence_semantics_attack_verifier_purity_explicit_work_root(tmp_path: Path) -> None:
    package = _copy(tmp_path)
    work_root = tmp_path / "work-base"
    work_root.mkdir(mode=0o700)
    before = _snapshot(package)
    completed = _run(package, tmp_path, work_root)
    assert completed.returncode == 0
    assert _snapshot(package) == before
    assert list(work_root.iterdir()) == []


def test_evidence_semantics_attack_verifier_purity_rejects_internal_work_root(tmp_path: Path) -> None:
    package = _copy(tmp_path)
    before = _snapshot(package)
    completed = _run(package, tmp_path, package / "VERIFY")
    assert completed.returncode != 0
    assert _error_code(completed) == "E_WORK_ROOT"
    assert _snapshot(package) == before


def test_evidence_semantics_attack_verifier_purity_failure_has_no_residue(tmp_path: Path) -> None:
    package = _copy(tmp_path)
    checksum = package / "SHA256SUMS.txt"
    checksum.write_bytes(checksum.read_bytes() + b"invalid\n")
    before = _snapshot(package)
    completed = _run(package, tmp_path)
    assert completed.returncode != 0
    assert _snapshot(package) == before
    assert not list(tmp_path.glob(".ac23-verify-*"))


def test_evidence_semantics_attack_verifier_purity_child_temp_and_git_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controlled = tmp_path / "controlled"
    controlled.mkdir()
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)
    monkeypatch.setattr(verifier, "_CONTROLLED_TEMP", os.fspath(controlled))
    verifier._git(tmp_path, "status")
    argv = captured["argv"]
    env = captured["env"]
    assert isinstance(argv, list)
    assert "maintenance.auto=0" in argv and "gc.auto=0" in argv
    assert isinstance(env, dict)
    assert env["TMPDIR"] == env["TEMP"] == env["TMP"] == os.fspath(controlled)


def test_evidence_semantics_attack_verifier_purity_cleanup_failure_is_nonpass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    workspace_holder: list[Path] = []

    def no_op_verify(*_args: object, **_kwargs: object) -> None:
        return None

    def fail_cleanup(workspace: Path) -> None:
        workspace_holder.append(workspace)
        raise verifier.VerificationError("E_WORK_ROOT_CLEANUP")

    monkeypatch.setattr(verifier, "verify", no_op_verify)
    monkeypatch.setattr(verifier, "_cleanup_work_root", fail_cleanup)
    with pytest.raises(verifier.VerificationError) as captured:
        verifier.verify_pure(package)
    assert captured.value.code == "E_WORK_ROOT_CLEANUP"
    assert workspace_holder
    shutil.rmtree(workspace_holder[0])


def test_evidence_semantics_attack_verifier_purity_input_mutation_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    package.mkdir()

    def mutate_then_fail(root: Path, *_args: object, **_kwargs: object) -> None:
        (root / "forbidden").write_bytes(b"x")
        raise verifier.VerificationError("E_SCHEMA")

    monkeypatch.setattr(verifier, "verify", mutate_then_fail)
    with pytest.raises(verifier.VerificationError) as captured:
        verifier.verify_pure(package)
    assert captured.value.code == "E_INPUT_MUTATED"
