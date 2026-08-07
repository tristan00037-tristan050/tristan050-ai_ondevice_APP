from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import threading
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from butler_pc_core.helper1.approval_closure import ROLE_MEDIA_TYPES
from butler_pc_core.helper1.approval_input import (
    APPROVAL_FILES,
    INVENTORY_NAME,
    LEGACY_FILES,
)

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "1" * 40
TREE = "2" * 40
WORKFLOW_PATH = ".github/workflows/helper1-v2-approval-evidence.yml"
WORKFLOW_REF = f"owner/repo/{WORKFLOW_PATH}@{COMMIT}"
ARTIFACT_NAME = "helper1-v2-approval-11-2"
WORKFLOW_ID = 17


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _artifact() -> bytes:
    files = {name: b"{}\n" for name in (*LEGACY_FILES, *APPROVAL_FILES)}
    object_raw = b"protected approval object"
    files[f"objects/{hashlib.sha256(object_raw).hexdigest()}"] = object_raw
    records: dict[str, object] = {}
    for name, raw in sorted(files.items()):
        role = None
        media_type = "application/octet-stream" if name.startswith("objects/") else "application/json"
        if name.startswith("approval/"):
            role = name.rsplit("/", 1)[1].rsplit(".", 2)[0]
            media_type = (
                ROLE_MEDIA_TYPES[role]
                if name.endswith(".payload.json")
                else "application/vnd.butler.helper1.evidence-envelope+json;v=1"
            )
        records[name] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "media_type": media_type,
            "role": role,
        }
    files[INVENTORY_NAME] = _canonical(
        {"schema_version": "butler.helper1.approval-input-inventory.v2", "files": records}
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    return stream.getvalue()


def _quality_artifact() -> bytes:
    from scripts.ci.helper1_quality_input_fetch import MANIFEST_NAME, SOURCE_FILES

    files = {name: f"fixture:{name}\n".encode() for name in SOURCE_FILES}
    manifest = {
        "schema_version": "butler.helper1.quality-input-manifest.v1",
        "files": {
            name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for name, raw in sorted(files.items())
        },
    }
    files[MANIFEST_NAME] = _canonical(manifest)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    return stream.getvalue()


@contextmanager
def _fake_github(
    *,
    bad_digest: bool = False,
    run_overrides: dict[str, object] | None = None,
    artifact_bytes: bytes | None = None,
    artifact_name: str = ARTIFACT_NAME,
) -> Iterator[tuple[str, bytes, bytes]]:
    artifact = artifact_bytes if artifact_bytes is not None else _artifact()
    workflow = b"name: protected-helper1-approval\n"
    state: dict[str, object] = {"base": ""}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/repos/owner/repo/actions/runs/11":
                run_body: dict[str, object] = {
                    "id": 11,
                    "run_attempt": 2,
                    "head_sha": COMMIT,
                    "event": "workflow_dispatch",
                    "workflow_id": WORKFLOW_ID,
                    "path": WORKFLOW_PATH,
                    "status": "completed",
                    "conclusion": "success",
                    "repository": {"id": 7, "full_name": "owner/repo"},
                }
                run_body.update(run_overrides or {})
                body = run_body
            elif path == "/repos/owner/repo/actions/artifacts/13":
                digest = "0" * 64 if bad_digest else hashlib.sha256(artifact).hexdigest()
                body = {
                    "id": 13,
                    "name": artifact_name,
                    "expired": False,
                    "digest": f"sha256:{digest}",
                    "archive_download_url": f"{state['base']}/download/13",
                    "workflow_run": {
                        "id": 11,
                        "head_sha": COMMIT,
                        "repository_id": 7,
                    },
                }
            elif path == f"/repos/owner/repo/contents/{WORKFLOW_PATH}":
                body = {
                    "encoding": "base64",
                    "content": base64.b64encode(workflow).decode("ascii"),
                }
            elif path == "/download/13":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(artifact)))
                self.end_headers()
                self.wfile.write(artifact)
                return
            else:
                self.send_error(404)
                return
            raw = _canonical(body)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state["base"] = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield str(state["base"]), artifact, workflow
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _fetch_command(
    base: str,
    artifact: Path,
    provenance: Path,
    workflow: bytes,
    *,
    workflow_ref: str = WORKFLOW_REF,
) -> list[str]:
    return [
        sys.executable,
        "scripts/ci/helper1_approval_input_fetch.py",
        "--api-base",
        base,
        "--repository",
        "owner/repo",
        "--repository-id",
        "7",
        "--run-id",
        "11",
        "--run-attempt",
        "2",
        "--artifact-id",
        "13",
        "--artifact-name",
        ARTIFACT_NAME,
        "--subject-commit",
        COMMIT,
        "--subject-tree",
        TREE,
        "--producer-workflow-ref",
        workflow_ref,
        "--producer-workflow-id",
        str(WORKFLOW_ID),
        "--producer-workflow-sha256",
        hashlib.sha256(workflow).hexdigest(),
        "--canonical-subject-sha256",
        "3" * 64,
        "--event-name",
        "workflow_dispatch",
        "--output-artifact",
        str(artifact),
        "--output-provenance",
        str(provenance),
    ]


def _quality_fetch_command(
    base: str,
    artifact: bytes,
    output_root: Path,
    workflow: bytes,
) -> list[str]:
    return [
        sys.executable,
        "scripts/ci/helper1_quality_input_fetch.py",
        "--api-base",
        base,
        "--repository",
        "owner/repo",
        "--repository-id",
        "7",
        "--run-id",
        "11",
        "--run-attempt",
        "2",
        "--artifact-id",
        "13",
        "--artifact-name",
        "quality-input",
        "--artifact-sha256",
        hashlib.sha256(artifact).hexdigest(),
        "--subject-commit",
        COMMIT,
        "--subject-tree",
        TREE,
        "--producer-workflow-ref",
        WORKFLOW_REF,
        "--producer-workflow-id",
        str(WORKFLOW_ID),
        "--producer-workflow-sha256",
        hashlib.sha256(workflow).hexdigest(),
        "--event-name",
        "workflow_dispatch",
        "--token-env",
        "HELPER1_TEST_TOKEN",
        "--output-root",
        str(output_root),
    ]


def _environment() -> dict[str, str]:
    return {**os.environ, "HELPER1_TEST_TOKEN": "memory-only", "PYTHONPATH": str(ROOT)}


def test_clean_runner_fetch_is_deterministic_and_verifiable(tmp_path: Path) -> None:
    with _fake_github() as (base, expected_artifact, workflow):
        outputs: list[tuple[bytes, bytes]] = []
        for suffix in ("a", "b"):
            artifact = tmp_path / suffix / "approval.zip"
            provenance = tmp_path / suffix / "provenance.json"
            command = _fetch_command(base, artifact, provenance, workflow)
            command.extend(("--token-env", "HELPER1_TEST_TOKEN"))
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stdout
            verdict, error = completed.stdout.splitlines()
            assert verdict.partition("=") == (
                "HELPER1_APPROVAL_INPUT_FETCH_OK",
                "=",
                "1",
            )
            assert error == "ERROR_CODE=NONE"
            assert artifact.read_bytes() == expected_artifact
            outputs.append((artifact.read_bytes(), provenance.read_bytes()))
        assert outputs[0] == outputs[1]

        verify = subprocess.run(
            [
                sys.executable,
                "scripts/ci/helper1_approval_input_verify.py",
                "--artifact",
                str(tmp_path / "a" / "approval.zip"),
                "--provenance",
                str(tmp_path / "a" / "provenance.json"),
                "--repository-id",
                "7",
                "--repository",
                "owner/repo",
                "--subject-commit",
                COMMIT,
                "--subject-tree",
                TREE,
                "--run-id",
                "11",
                "--run-attempt",
                "2",
                "--workflow-ref",
                WORKFLOW_REF,
                "--workflow-id",
                str(WORKFLOW_ID),
                "--workflow-sha256",
                hashlib.sha256(workflow).hexdigest(),
                "--artifact-id",
                "13",
                "--artifact-name",
                ARTIFACT_NAME,
                "--canonical-subject-sha256",
                "3" * 64,
            ],
            cwd=ROOT,
            env=_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        assert verify.returncode == 0, verify.stdout


def test_quality_fetch_accepts_real_nested_artifact_shape(tmp_path: Path) -> None:
    artifact = _quality_artifact()
    with _fake_github(
        artifact_bytes=artifact,
        artifact_name="quality-input",
    ) as (base, expected_artifact, workflow):
        output_root = tmp_path / "quality"
        completed = subprocess.run(
            _quality_fetch_command(base, expected_artifact, output_root, workflow),
            cwd=ROOT,
            env=_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
    assert completed.returncode == 0, completed.stdout
    verdict, error = completed.stdout.splitlines()
    assert verdict.partition("=") == ("HELPER1_QUALITY_INPUT_FETCH_OK", "=", "1")
    assert error == "ERROR_CODE=NONE"
    assert (output_root / "QUALITY_INPUT_PROVENANCE.v1.json").is_file()


def test_clean_runner_rejects_api_artifact_digest_mismatch(tmp_path: Path) -> None:
    with _fake_github(bad_digest=True) as (base, _artifact_raw, workflow):
        command = _fetch_command(base, tmp_path / "approval.zip", tmp_path / "p.json", workflow)
        command.extend(("--token-env", "HELPER1_TEST_TOKEN"))
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
    assert completed.returncode == 1
    assert completed.stdout.splitlines() == [
        "HELPER1_APPROVAL_INPUT_FETCH_OK=0",
        "ERROR_CODE=ARTIFACT_DIGEST_MISMATCH",
    ]
    assert not (tmp_path / "approval.zip").exists()


def test_clean_runner_rejects_conflicting_workflow_and_non_success_runs(tmp_path: Path) -> None:
    attacks = (
        {"workflow_id": 999},
        {"path": ".github/workflows/unprotected-attacker.yml"},
        {"status": "in_progress", "conclusion": None},
        {"status": "completed", "conclusion": "failure"},
        {"run_attempt": 3},
    )
    for index, override in enumerate(attacks):
        with _fake_github(run_overrides=override) as (base, _artifact_raw, workflow):
            command = _fetch_command(
                base,
                tmp_path / str(index) / "approval.zip",
                tmp_path / str(index) / "p.json",
                workflow,
            )
            command.extend(("--token-env", "HELPER1_TEST_TOKEN"))
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
        assert completed.returncode == 1
        assert completed.stdout.splitlines() == [
            "HELPER1_APPROVAL_INPUT_FETCH_OK=0",
            "ERROR_CODE=PRODUCER_RUN_MISMATCH",
        ]


def test_workflow_ref_commit_must_equal_run_head(tmp_path: Path) -> None:
    mismatched_ref = f"owner/repo/{WORKFLOW_PATH}@{'4' * 40}"
    workflow = b"name: protected-helper1-approval\n"
    command = _fetch_command(
        "https://api.invalid",
        tmp_path / "approval.zip",
        tmp_path / "provenance.json",
        workflow,
        workflow_ref=mismatched_ref,
    )
    command.extend(("--token-env", "HELPER1_TEST_TOKEN"))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout.splitlines() == [
        "HELPER1_APPROVAL_INPUT_FETCH_OK=0",
        "ERROR_CODE=PRODUCER_RUN_MISMATCH",
    ]
    assert not (tmp_path / "approval.zip").exists()


def test_quality_input_workflow_ref_commit_must_equal_run_head(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ci/helper1_quality_input_fetch.py",
            "--api-base",
            "https://api.invalid",
            "--repository",
            "owner/repo",
            "--repository-id",
            "7",
            "--run-id",
            "11",
            "--run-attempt",
            "2",
            "--artifact-id",
            "13",
            "--artifact-name",
            "quality-input",
            "--artifact-sha256",
            "5" * 64,
            "--subject-commit",
            COMMIT,
            "--subject-tree",
            TREE,
            "--producer-workflow-ref",
            f"owner/repo/{WORKFLOW_PATH}@{'4' * 40}",
            "--producer-workflow-id",
            str(WORKFLOW_ID),
            "--producer-workflow-sha256",
            "6" * 64,
            "--event-name",
            "workflow_dispatch",
            "--token-env",
            "HELPER1_TEST_TOKEN",
            "--output-root",
            str(tmp_path / "quality"),
        ],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout.splitlines() == [
        "HELPER1_QUALITY_INPUT_FETCH_OK=0",
        "ERROR_CODE=QUALITY_INPUT_PRODUCER_INVALID",
    ]
    assert not (tmp_path / "quality").exists()


def test_actual_run_fixture_keeps_workflow_run_name_distinct_from_pr_check_name() -> None:
    fixture = json.loads(
        (
            ROOT
            / "tests/fixtures/helper1_v2/github_run_30883847088.json"
        ).read_text(encoding="utf-8")
    )
    assert fixture == {
        "conclusion": "success",
        "event": "pull_request",
        "head_sha": "de39aca689bf56a51875c3755cc6a59032b19cda",
        "name": "helper1-v2-evidence-producer",
        "path": ".github/workflows/helper1-v2-evidence.yml",
        "status": "completed",
        "workflow_id": 326757693,
    }
    assert fixture["name"] != "helper1-v2-untrusted-evidence"


def test_actual_artifact_fixture_contains_only_documented_nested_run_identity() -> None:
    fixture = json.loads(
        (
            ROOT
            / "tests/fixtures/helper1_v2/github_artifact_8882308140.json"
        ).read_text(encoding="utf-8")
    )
    assert fixture == {
        "id": 8882308140,
        "name": "helper1-v2-evidence-30883847088-1",
        "size_in_bytes": 814,
        "expired": False,
        "digest": "sha256:7d8ff01488fce8ce7be14a8bbe601ed81ae45abd868d7247f162b1b88546cd8f",
        "workflow_run": {
            "id": 30883847088,
            "repository_id": 1097940756,
            "head_repository_id": 1097940756,
            "head_branch": "feat/helper1-v2-a4-lineage-13r",
            "head_sha": "de39aca689bf56a51875c3755cc6a59032b19cda",
        },
    }
    assert set(fixture["workflow_run"]) == {
        "head_branch",
        "head_repository_id",
        "head_sha",
        "id",
        "repository_id",
    }
    assert "workflow_id" not in fixture["workflow_run"]
