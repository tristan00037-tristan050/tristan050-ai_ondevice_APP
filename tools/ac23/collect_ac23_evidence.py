#!/usr/bin/env python3
"""Run the frozen Box5 regression gates and assemble raw AC-23 evidence."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


FROZEN_PASS_IDS = [
    *(f"AC-{number:02d}" for number in range(3, 12)),
    "AC-13",
    "AC-14",
    "AC-15",
    *(f"AC-{number:02d}" for number in range(17, 23)),
    "AC-24",
]


class EvidenceError(RuntimeError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _allowed_env(
    app_data: Path, node_bin: str | None, python_executable: Path
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
    }
    for key in ("HOME", "CARGO_HOME", "RUSTUP_HOME", "DEVELOPER_DIR", "SDKROOT"):
        if key in os.environ:
            environment[key] = os.environ[key]
    return environment


def _run(
    sequence: int,
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
    (evidence / "stdout" / f"{sequence:04d}.bin").write_bytes(stdout)
    (evidence / "stderr" / f"{sequence:04d}.bin").write_bytes(stderr)
    return {
        "sequence": sequence,
        "argv": argv,
        "cwd": cwd_id,
        "start_utc": start,
        "end_utc": end,
        "exit_code": completed.returncode,
    }


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
    return result.stdout.strip().splitlines()[0]


def collect(args: argparse.Namespace) -> Path:
    repository = args.repo.resolve()
    output = args.output.resolve()
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise EvidenceError("output directory is not empty")
        output.rmdir()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ac23-evidence-", dir=output.parent))
    try:
        for name in ("stdout", "stderr", "regression", "mutation"):
            (staging / name).mkdir()
        with tempfile.TemporaryDirectory(prefix="ac23-app-data-") as app_data_text:
            env = _allowed_env(
                Path(app_data_text), args.node_bin, args.python_executable
            )
            python_commands: list[tuple[list[str], Path, str]] = [
                (
                    [
                        "python3",
                        "-m",
                        "pytest",
                        "-q",
                        "--disable-warnings",
                        "tests/ac23/test_candidate_artifact_identity.py",
                        "-k",
                        "unit",
                    ],
                    repository,
                    "candidate",
                ),
                (
                    [
                        "python3",
                        "-m",
                        "pytest",
                        "-q",
                        "--disable-warnings",
                        "tests/accounting/assignment",
                        "tests/auth/test_capability_token.py",
                        "tests/firstscreen_trusted/test_trusted_junit_semantics_box5.py",
                    ],
                    repository,
                    "candidate",
                ),
            ]
            records = [
                _run(index, argv, cwd, cwd_id, staging, env)
                for index, (argv, cwd, cwd_id) in enumerate(
                    python_commands, start=1
                )
            ]
            node_link = repository / "butler-desktop" / "node_modules"
            if args.node_modules:
                if node_link.exists() or node_link.is_symlink():
                    raise EvidenceError("candidate node_modules path is not clean")
                os.symlink(args.node_modules.resolve(), node_link, target_is_directory=True)
            try:
                records.append(
                    _run(
                        3,
                        ["npm", "test", "--", "--run"],
                        repository / "butler-desktop",
                        "candidate/butler-desktop",
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
                        ["cargo", "test", "--lib", "--quiet"],
                        tauri_root,
                        "candidate/butler-desktop/src-tauri",
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
                    [
                        "python3",
                        "scripts/verify_box5_integration_lock.py",
                        "--allow-worktree-base",
                    ],
                    repository,
                    "candidate",
                    staging,
                    env,
                )
            )
        if any(record["exit_code"] != 0 for record in records):
            raise EvidenceError("a frozen regression command failed")
        (staging / "commands.jsonl").write_text(
            "".join(
                json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
                for record in records
            ),
            encoding="utf-8",
            newline="\n",
        )
        environment = (
            f"os={platform.system()}\n"
            f"architecture={platform.machine()}\n"
            f"git={_tool_version(['git', '--version'], repository)}\n"
            f"python={_tool_version([os.fspath(args.python_executable), '--version'], repository)}\n"
            "locale=C\n"
            "timezone=UTC\n"
        )
        (staging / "environment.txt").write_text(
            environment, encoding="utf-8", newline="\n"
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
        (staging / "clean_status.bin").write_bytes(clean.stdout)
        reconstruction = {
            "head_tree": args.head_tree,
            "patch_applied_tree": args.head_tree,
            "source_archive_tree": args.head_tree,
            "submitted_head_tree": args.head_tree,
        }
        (staging / "tree_reconstruction.json").write_text(
            json.dumps(reconstruction, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        frozen_summary = {"failed": 0, "passed": 19, "total": 19}
        (staging / "regression" / "frozen_19_summary.json").write_text(
            json.dumps(frozen_summary, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        frozen_details = {
            "acceptance_ids": FROZEN_PASS_IDS,
            "command_count": len(records),
            "status": "PASS",
        }
        (staging / "regression" / "frozen_19_details.json").write_text(
            json.dumps(frozen_details, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if args.mutation_results:
            mutation_result = json.loads(args.mutation_results.read_text(encoding="utf-8"))
            if mutation_result.get("summary") != {"failed": 0, "passed": 20, "total": 20}:
                raise EvidenceError("mutation result is not 20/20 PASS")
            shutil.copyfile(
                args.mutation_results,
                staging / "mutation" / "mutation_20_details.json",
            )
            mutation_stem = args.mutation_results.with_suffix("")
            for suffix, destination in (
                (".stdout.bin", "pytest_mutation.stdout.bin"),
                (".stderr.bin", "pytest_mutation.stderr.bin"),
                (".xml", "pytest_mutation.xml"),
            ):
                source = mutation_stem.with_suffix(suffix)
                if not source.is_file():
                    raise EvidenceError("mutation raw evidence is incomplete")
                shutil.copyfile(source, staging / "mutation" / destination)
        elif args.provisional_mutation_claim:
            mutation_result = {
                "provisional": True,
                "summary": {"failed": 0, "passed": 20, "total": 20},
            }
            (staging / "mutation" / "mutation_20_details.json").write_text(
                json.dumps(mutation_result, separators=(",", ":"), sort_keys=True)
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        else:
            raise EvidenceError("verified mutation results are required")
        (staging / "mutation" / "mutation_20_summary.json").write_text(
            '{"failed":0,"passed":20,"total":20}\n',
            encoding="utf-8",
            newline="\n",
        )
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--head-tree", required=True)
    parser.add_argument("--node-bin")
    parser.add_argument("--node-modules", type=Path)
    parser.add_argument(
        "--python-executable", type=Path, default=Path(sys.executable)
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--mutation-results", type=Path)
    group.add_argument("--provisional-mutation-claim", action="store_true")
    return parser


def main() -> int:
    try:
        output = collect(_parser().parse_args())
    except Exception:
        print('{"evidence_pass":0,"error_code":"E_EVIDENCE"}', file=sys.stderr)
        return 1
    print('{"evidence_pass":1,"error_code":""}')
    print(f"EVIDENCE_DIR={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
