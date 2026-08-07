#!/usr/bin/env python3
"""Fetch and safely materialize one exact protected SearchQuality input artifact."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import stat
import sys
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci.helper1_approval_input_fetch import (  # noqa: E402
    WORKFLOW_REF,
    _json,
    _request,
)

SOURCE_FILES = frozenset(
    {
        "corpus-manifest.json",
        "queries.jsonl",
        "retrieval-policy.json",
        "M3/native-measurement.json",
        "M3/raw-bundle.json",
        "M3/device-receipt.json",
        "M3/observer.bin",
        "M4/native-measurement.json",
        "M4/raw-bundle.json",
        "M4/device-receipt.json",
        "M4/observer.bin",
    }
)
MANIFEST_NAME = "QUALITY_INPUT_MANIFEST.v1.json"
PROVENANCE_NAME = "QUALITY_INPUT_PROVENANCE.v1.json"
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class QualityInputError(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _object(raw: bytes) -> dict[str, object]:
    value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if type(value) is not dict:
        raise ValueError
    return value


def _archive(raw: bytes) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    folded: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                mode = item.external_attr >> 16
                if (
                    item.is_dir()
                    or path.is_absolute()
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or "\\" in item.filename
                    or len(path.parts) != 1 and path.parts[0] not in {"M3", "M4"}
                    or (mode and (stat.S_ISLNK(mode) or not stat.S_ISREG(mode)))
                    or item.file_size < 1
                    or item.file_size > MAX_FILE_BYTES
                    or item.filename.casefold() in folded
                ):
                    raise QualityInputError("QUALITY_INPUT_ARCHIVE_INVALID")
                payload = archive.read(item)
                total += len(payload)
                if len(payload) != item.file_size or total > MAX_TOTAL_BYTES:
                    raise QualityInputError("QUALITY_INPUT_ARCHIVE_INVALID")
                files[item.filename] = payload
                folded.add(item.filename.casefold())
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise QualityInputError("QUALITY_INPUT_ARCHIVE_INVALID") from exc
    if set(files) != SOURCE_FILES | {MANIFEST_NAME}:
        raise QualityInputError("QUALITY_INPUT_INVENTORY_INVALID")
    manifest = _object(files[MANIFEST_NAME])
    records = manifest.get("files")
    if (
        manifest.get("schema_version") != "butler.helper1.quality-input-manifest.v1"
        or type(records) is not dict
        or set(records) != SOURCE_FILES
        or _canonical(manifest) + b"\n" != files[MANIFEST_NAME]
    ):
        raise QualityInputError("QUALITY_INPUT_INVENTORY_INVALID")
    for name in SOURCE_FILES:
        record = records.get(name)
        payload = files[name]
        if (
            type(record) is not dict
            or set(record) != {"bytes", "sha256"}
            or record.get("bytes") != len(payload)
            or record.get("sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise QualityInputError("QUALITY_INPUT_INVENTORY_INVALID")
    return files


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="https://api.github.com")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--subject-commit", required=True)
    parser.add_argument("--subject-tree", required=True)
    parser.add_argument("--producer-workflow-ref", required=True)
    parser.add_argument("--producer-workflow-id", required=True, type=int)
    parser.add_argument("--producer-workflow-sha256", required=True)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        token = os.environ.get(args.token_env)
        match = WORKFLOW_REF.fullmatch(args.producer_workflow_ref)
        if (
            not token
            or match is None
            or match.group("repository") != args.repository
            or match.group("sha") != args.subject_commit
            or SHA40.fullmatch(args.subject_commit) is None
            or SHA40.fullmatch(args.subject_tree) is None
            or SHA256.fullmatch(args.artifact_sha256) is None
            or SHA256.fullmatch(args.producer_workflow_sha256) is None
        ):
            raise QualityInputError("QUALITY_INPUT_PRODUCER_INVALID")
        base = args.api_base.rstrip("/")
        run = _json(f"{base}/repos/{args.repository}/actions/runs/{args.run_id}", token)
        repository = run.get("repository")
        if (
            type(repository) is not dict
            or repository.get("id") != args.repository_id
            or repository.get("full_name") != args.repository
            or run.get("id") != args.run_id
            or run.get("run_attempt") != args.run_attempt
            or run.get("head_sha") != args.subject_commit
            or run.get("event") != args.event_name
            or run.get("workflow_id") != args.producer_workflow_id
            or run.get("path") != match.group("path")
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
        ):
            raise QualityInputError("QUALITY_INPUT_PRODUCER_INVALID")
        artifact = _json(
            f"{base}/repos/{args.repository}/actions/artifacts/{args.artifact_id}", token
        )
        artifact_run = artifact.get("workflow_run")
        if (
            artifact.get("id") != args.artifact_id
            or artifact.get("name") != args.artifact_name
            or artifact.get("expired") is not False
            or type(artifact_run) is not dict
            or artifact_run.get("id") != args.run_id
            or artifact_run.get("head_sha") != args.subject_commit
            or artifact_run.get("repository_id") != args.repository_id
        ):
            raise QualityInputError("QUALITY_INPUT_PRODUCER_INVALID")
        workflow_path = urllib.parse.quote(match.group("path"), safe="/")
        workflow = _json(
            f"{base}/repos/{args.repository}/contents/{workflow_path}?ref={match.group('sha')}",
            token,
        )
        if workflow.get("encoding") != "base64" or type(workflow.get("content")) is not str:
            raise QualityInputError("QUALITY_INPUT_PRODUCER_INVALID")
        workflow_bytes = base64.b64decode(workflow["content"], validate=True)
        if hashlib.sha256(workflow_bytes).hexdigest() != args.producer_workflow_sha256:
            raise QualityInputError("QUALITY_INPUT_PRODUCER_INVALID")
        download_url = artifact.get("archive_download_url")
        if type(download_url) is not str or not download_url.startswith(base + "/"):
            raise QualityInputError("QUALITY_INPUT_PRODUCER_INVALID")
        artifact_bytes = _request(download_url, token, accept="application/octet-stream")
        observed_digest = hashlib.sha256(artifact_bytes).hexdigest()
        if (
            observed_digest != args.artifact_sha256
            or artifact.get("digest") != f"sha256:{observed_digest}"
        ):
            raise QualityInputError("QUALITY_INPUT_DIGEST_MISMATCH")
        files = _archive(artifact_bytes)
        provenance = {
            "schema_version": "butler.helper1.quality-input-provenance.v1",
            "repository_id": args.repository_id,
            "repository_name": args.repository,
            "subject_commit": args.subject_commit,
            "subject_tree": args.subject_tree,
            "producer_workflow_ref": args.producer_workflow_ref,
            "producer_workflow_id": args.producer_workflow_id,
            "producer_workflow_sha256": args.producer_workflow_sha256,
            "run_id": args.run_id,
            "run_attempt": args.run_attempt,
            "event_name": args.event_name,
            "artifact_id": args.artifact_id,
            "artifact_name": args.artifact_name,
            "artifact_sha256": observed_digest,
        }
        for name, payload in files.items():
            _write(args.output_root / name, payload)
        _write(args.output_root / PROVENANCE_NAME, _canonical(provenance) + b"\n")
    except (OSError, ValueError, TypeError, QualityInputError):
        print("HELPER1_QUALITY_INPUT_FETCH_OK=0")
        print("ERROR_CODE=QUALITY_INPUT_PRODUCER_INVALID")
        return 1
    print("HELPER1_QUALITY_INPUT_FETCH_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
