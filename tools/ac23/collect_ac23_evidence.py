#!/usr/bin/env python3
"""Run the frozen Box5 regression gates and assemble raw AC-23 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from junit_closed_profile import JunitProfileError, parse_pytest_junit_closed
from verify_candidate_artifact_identity import (
    APPROVED_BASE_COMMIT,
    load_evidence_policy,
    verify_mutation_results,
)


class EvidenceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _allowed_env(
    app_data: Path,
    temp_root: Path,
    node_bin: str | None,
    python_executable: Path,
) -> dict[str, str]:
    path = os.environ.get("PATH", "")
    path = os.fspath(python_executable.parent) + os.pathsep + path
    if node_bin:
        path = node_bin + os.pathsep + path
    environment = {
        "PATH": path,
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
        "BUTLER_APP_DATA_DIR": os.fspath(app_data),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "TMPDIR": os.fspath(temp_root),
        "TEMP": os.fspath(temp_root),
        "TMP": os.fspath(temp_root),
    }
    for key in ("HOME", "CARGO_HOME", "RUSTUP_HOME", "DEVELOPER_DIR", "SDKROOT"):
        if key in os.environ:
            environment[key] = os.environ[key]
    return environment


def _run(
    sequence: int,
    run_id: str,
    argv: list[str],
    cwd: Path,
    cwd_id: str,
    evidence: Path,
    env: dict[str, str],
) -> dict[str, object]:
    start = _utc()
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    end = _utc()
    candidate_root = cwd
    for _ in range(len(Path(cwd_id).parts) - 1):
        candidate_root = candidate_root.parent
    replacements = (
        (os.fsencode(candidate_root), b"<candidate>"),
        (os.fsencode(Path.home()), b"<user-home>"),
    )
    stdout = completed.stdout
    stderr = completed.stderr
    for source, replacement in replacements:
        stdout = stdout.replace(source, replacement)
        stderr = stderr.replace(source, replacement)
    stdout_path = evidence / "stdout" / f"{sequence:04d}.bin"
    stderr_path = evidence / "stderr" / f"{sequence:04d}.bin"
    _atomic_write(stdout_path, stdout)
    _atomic_write(stderr_path, stderr)
    return {
        "sequence": sequence,
        "run_id": run_id,
        "argv": argv,
        "cwd": cwd_id,
        "start_utc": start,
        "end_utc": end,
        "exit_code": completed.returncode,
        "termination": "exit" if completed.returncode >= 0 else "signal",
        "stdout_path": f"stdout/{sequence:04d}.bin",
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_path": f"stderr/{sequence:04d}.bin",
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    }


def _git(repository: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        [
            "git", "-c", "core.autocrlf=false", "-c", "core.filemode=true",
            "-c", "maintenance.auto=0", "-c", "gc.auto=0", *args,
        ],
        cwd=repository,
        env={
            "PATH": os.environ.get("PATH", ""),
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise EvidenceError("E_TREE_RECONSTRUCTION")
    return completed.stdout


def _tree_reconstruction(
    repository: Path, base: str, temporary_parent: Path
) -> dict[str, str]:
    head_commit = _git(repository, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    head_tree = _git(repository, "rev-parse", "--verify", "HEAD^{tree}").decode().strip()
    with tempfile.TemporaryDirectory(
        prefix="ac23-tree-evidence-", dir=temporary_parent
    ) as temporary_text:
        temporary = Path(temporary_text)
        patch = temporary / "candidate.patch"
        patch.write_bytes(_git(repository, "diff", "--binary", "--full-index", "--no-renames", base, head_commit, "--"))
        patch_repo = temporary / "patch"
        patch_repo.mkdir()
        _git(patch_repo, "init", "--quiet")
        _git(patch_repo, "fetch", "--no-tags", os.fspath(repository), base)
        _git(patch_repo, "checkout", "--detach", "--force", "FETCH_HEAD")
        _git(patch_repo, "apply", "--binary", "--index", os.fspath(patch))
        patch_tree = _git(patch_repo, "write-tree").decode().strip()

        source_tar = temporary / "source.tar"
        source_tar.write_bytes(_git(repository, "archive", "--format=tar", "--prefix=candidate/", head_commit))
        source_root = temporary / "source"
        source_root.mkdir()
        with tarfile.open(source_tar, "r:") as archive:
            archive.extractall(source_root, filter="data")
        source_repo = source_root / "candidate"
        _git(source_repo, "init", "--quiet")
        _git(source_repo, "add", "-f", "-A")
        source_tree = _git(source_repo, "write-tree").decode().strip()
    if len({head_tree, patch_tree, source_tree}) != 1:
        raise EvidenceError("E_TREE_RECONSTRUCTION")
    return {
        "head_commit": head_commit,
        "head_tree": head_tree,
        "patch_applied_tree": patch_tree,
        "source_archive_tree": source_tree,
        "submitted_head_tree": head_tree,
        "patch_command_id": "git-apply-index-v1",
        "source_reconstruction_id": "git-archive-index-v1",
    }


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        elif path.is_dir():
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _tool_version(argv: list[str], cwd: Path) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env={
            "PATH": os.environ.get("PATH", ""),
            "LC_ALL": "C",
            "TZ": "UTC",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    lines = result.stdout.strip().splitlines()
    if result.returncode != 0 or not lines:
        raise EvidenceError("E_TOOLCHAIN")
    return lines[0]


def collect(args: argparse.Namespace) -> Path:
    repository = args.repo.resolve()
    output = args.output.resolve()
    policy_path = args.policy.resolve()
    policy_bytes = policy_path.read_bytes()
    policy = load_evidence_policy(policy_bytes)
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise EvidenceError("output directory is not empty")
        output.rmdir()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ac23-evidence-", dir=output.parent))
    try:
        for name in ("stdout", "stderr", "junit", "canonical", "mutation"):
            (staging / name).mkdir()
        run_junit = repository / "tests" / "ac23" / ".ac23-evidence"
        if run_junit.exists() or run_junit.is_symlink():
            raise EvidenceError("E_OUTPUT_NOT_CLEAN")
        run_junit.mkdir()
        controlled_temp = staging / "controlled-temp"
        controlled_temp.mkdir(mode=0o700)
        with tempfile.TemporaryDirectory(
            prefix="ac23-app-data-", dir=staging
        ) as app_data_text:
            env = _allowed_env(
                Path(app_data_text),
                controlled_temp,
                args.node_bin,
                args.python_executable,
            )
            runs = policy["required_runs"]
            records = [
                _run(index, run["run_id"], run["argv"], repository, run["cwd"], staging, env)
                for index, run in enumerate(runs[:2], start=1)
            ]
            for index in (1, 2):
                source = run_junit / f"run-{index:04d}.xml"
                if not source.is_file():
                    raise EvidenceError("E_RAW_EVIDENCE_MISSING")
                shutil.copyfile(source, staging / "junit" / f"{index:04d}.xml")
            shutil.rmtree(run_junit)
            node_link = repository / "butler-desktop" / "node_modules"
            if args.node_modules:
                if node_link.exists() or node_link.is_symlink():
                    raise EvidenceError("candidate node_modules path is not clean")
                os.symlink(args.node_modules.resolve(), node_link, target_is_directory=True)
            try:
                records.append(
                    _run(
                        3,
                        runs[2]["run_id"],
                        runs[2]["argv"],
                        repository / "butler-desktop",
                        runs[2]["cwd"],
                        staging,
                        env,
                    )
                )
            finally:
                if args.node_modules:
                    node_link.unlink()
            tauri_root = repository / "butler-desktop" / "src-tauri"
            created_resource_directories: list[Path] = []
            for resource_name in ("models", "python-runtime"):
                resource = tauri_root / resource_name
                if not resource.exists():
                    resource.mkdir()
                    created_resource_directories.append(resource)
            try:
                records.append(
                    _run(
                        4,
                        runs[3]["run_id"],
                        runs[3]["argv"],
                        tauri_root,
                        runs[3]["cwd"],
                        staging,
                        env,
                    )
                )
            finally:
                for resource in reversed(created_resource_directories):
                    resource.rmdir()
            records.append(
                _run(
                    5,
                    runs[4]["run_id"],
                    runs[4]["argv"],
                    repository,
                    runs[4]["cwd"],
                    staging,
                    env,
                )
            )
        failed_runs = [
            str(record["run_id"]).upper().replace("-", "_")
            for record in records
            if record["exit_code"] != 0 or record["termination"] != "exit"
        ]
        if failed_runs:
            raise EvidenceError("E_COMMAND_FAILED_" + failed_runs[0])
        _atomic_write(
            staging / "commands.jsonl",
            "".join(
                json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
                for record in records
            ).encode("utf-8"),
        )
        limits = policy["limits"]
        for run in policy["required_runs"]:
            if run["parser"] != "pytest-junit-pass-v2":
                continue
            try:
                canonical = parse_pytest_junit_closed(
                    (staging / run["result_path"]).read_bytes(),
                    expected_testcase_ids=frozenset(run["expected_testcase_ids"]),
                    max_bytes=limits["max_junit_bytes"],
                    max_elements=limits["max_xml_elements"],
                    max_testcases_per_run=limits["max_testcases_per_run"],
                    max_attribute_count_per_element=limits["max_attribute_count_per_element"],
                    max_attribute_value_bytes=limits["max_attribute_value_bytes"],
                    max_testcase_id_bytes=limits["max_testcase_id_bytes"],
                )
            except JunitProfileError as error:
                raise EvidenceError(error.code) from error
            _atomic_write(staging / run["canonical_result_path"], canonical.to_bytes())
        environment = {
            "os": platform.system(),
            "architecture": platform.machine(),
            "git": _tool_version(["git", "--version"], repository),
            "python": _tool_version([os.fspath(args.python_executable), "--version"], repository),
            "locale": "C",
            "timezone": "UTC",
        }
        _atomic_write(
            staging / "environment.json",
            (
                json.dumps(environment, separators=(",", ":"), sort_keys=True)
                + "\n"
            ).encode("utf-8"),
        )
        toolchain = {
            "python_executable_sha256": _sha256_file(args.python_executable.resolve()),
            "python_version": _tool_version([os.fspath(args.python_executable), "--version"], repository),
            "pytest_version": _tool_version([os.fspath(args.python_executable), "-m", "pytest", "--version"], repository),
            "node_version": _tool_version(["node", "--version"], repository),
            "npm_version": _tool_version(["npm", "--version"], repository),
            "cargo_version": _tool_version(["cargo", "--version"], repository),
            "rustc_version": _tool_version(["rustc", "--version"], repository),
            "git_version": _tool_version(["git", "--version"], repository),
        }
        _atomic_write(
            staging / "toolchain.json",
            (
                json.dumps(toolchain, separators=(",", ":"), sort_keys=True)
                + "\n"
            ).encode("utf-8"),
        )
        clean = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=repository,
            env={
                "PATH": os.environ.get("PATH", ""),
                "LC_ALL": "C",
                "TZ": "UTC",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if clean.returncode != 0 or clean.stdout:
            raise EvidenceError("candidate worktree is not clean")
        _atomic_write(staging / "clean_status.bin", clean.stdout)
        reconstruction = _tree_reconstruction(
            repository, args.base_commit, controlled_temp
        )
        _atomic_write(
            staging / "tree_reconstruction.json",
            (
                json.dumps(reconstruction, separators=(",", ":"), sort_keys=True)
                + "\n"
            ).encode("utf-8"),
        )
        mutation_stem = args.mutation_results.with_suffix("")
        mutation_sources = {
            "mutation/mutation_results_v3.json": args.mutation_results,
            "mutation/pytest_mutation.stdout.bin": mutation_stem.with_suffix(".stdout.bin"),
            "mutation/pytest_mutation.stderr.bin": mutation_stem.with_suffix(".stderr.bin"),
            "mutation/pytest_mutation.xml": mutation_stem.with_suffix(".xml"),
            "mutation/canonical.json": mutation_stem.with_suffix(".canonical.json"),
        }
        if not all(path.is_file() and not path.is_symlink() for path in mutation_sources.values()):
            raise EvidenceError("E_RAW_EVIDENCE_MISSING")
        mutation_payloads = {
            relative: source.read_bytes()
            for relative, source in mutation_sources.items()
        }
        verify_mutation_results(mutation_payloads, policy)
        for relative, source in mutation_sources.items():
            shutil.copyfile(source, staging / relative)
        shutil.copyfile(
            args.mutation_results,
            staging / "mutation/mutation_results_v2.json",
        )
        shutil.rmtree(controlled_temp)
        if controlled_temp.exists() or controlled_temp.is_symlink():
            raise EvidenceError("E_WORK_ROOT_CLEANUP")
        actual_inventory = sorted(
            path.relative_to(staging).as_posix()
            for path in staging.rglob("*")
            if path.is_file()
        )
        if actual_inventory != policy["evidence_inventory"]:
            raise EvidenceError("E_EVIDENCE_INVENTORY")
        _fsync_tree(staging)
        os.replace(staging, output)
    except Exception:
        if 'run_junit' in locals() and (run_junit.exists() or run_junit.is_symlink()):
            shutil.rmtree(run_junit)
        if staging.exists() or staging.is_symlink():
            shutil.rmtree(staging)
        raise
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-commit", default=APPROVED_BASE_COMMIT)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).with_name("evidence_policy_v3.json"),
    )
    parser.add_argument("--node-bin")
    parser.add_argument("--node-modules", type=Path)
    parser.add_argument(
        "--python-executable", type=Path, default=Path(sys.executable)
    )
    parser.add_argument("--mutation-results", type=Path, required=True)
    return parser


def main() -> int:
    try:
        output = collect(_parser().parse_args())
    except Exception as error:
        code = error.code if isinstance(error, EvidenceError) else "E_EVIDENCE"
        print(json.dumps({"evidence_pass": 0, "error_code": code}, separators=(",", ":"), sort_keys=True), file=sys.stderr)
        return 1
    print('{"evidence_pass":1,"error_code":""}')
    print(f"EVIDENCE_DIR={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
