#!/usr/bin/env python3
"""Fetch one explicitly selected Helper1 approval artifact from GitHub."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.approval_input import (  # noqa: E402
    ApprovalInputProvenanceV2,
    inspect_approval_input_bytes,
)
from butler_pc_core.helper1.failure_codes import Helper1FailureCode, Helper1V61Error  # noqa: E402

API_VERSION = "2026-03-10"
WORKFLOW_REF = re.compile(
    r"^(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/(?P<path>\.github/workflows/[A-Za-z0-9_.-]+)@(?P<sha>[0-9a-f]{40})$"
)
MAX_RESPONSE_BYTES = 160 * 1024 * 1024


def _request(url: str, token: str, *, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "butler-helper1-approval-fetch-v2",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > MAX_RESPONSE_BYTES:
                raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise Helper1V61Error(Helper1FailureCode.NO_EXPLICIT_PRODUCER) from exc
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
    return raw


def _json(url: str, token: str) -> dict[str, object]:
    try:
        value = json.loads(_request(url, token, accept="application/vnd.github+json"))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise Helper1V61Error(Helper1FailureCode.NO_EXPLICIT_PRODUCER) from exc
    if not isinstance(value, dict):
        raise Helper1V61Error(Helper1FailureCode.NO_EXPLICIT_PRODUCER)
    return value


def _write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="https://api.github.com")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--subject-commit", required=True)
    parser.add_argument("--subject-tree", required=True)
    parser.add_argument("--producer-workflow-ref", required=True)
    parser.add_argument("--producer-workflow-id", required=True, type=int)
    parser.add_argument("--producer-workflow-sha256", required=True)
    parser.add_argument("--canonical-subject-sha256", required=True)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--output-artifact", required=True, type=Path)
    parser.add_argument("--output-provenance", required=True, type=Path)
    args = parser.parse_args()
    try:
        token = os.environ.get(args.token_env)
        if not token:
            raise Helper1V61Error(Helper1FailureCode.NO_EXPLICIT_PRODUCER)
        match = WORKFLOW_REF.fullmatch(args.producer_workflow_ref)
        if match is None or match.group("repository") != args.repository:
            raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH)
        if match.group("sha") != args.subject_commit:
            raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH)
        base = args.api_base.rstrip("/")
        run = _json(f"{base}/repos/{args.repository}/actions/runs/{args.run_id}", token)
        repository = run.get("repository")
        expected_workflow_path = match.group("path")
        if (
            not isinstance(repository, dict)
            or repository.get("id") != args.repository_id
            or repository.get("full_name") != args.repository
            or run.get("id") != args.run_id
            or run.get("run_attempt") != args.run_attempt
            or run.get("head_sha") != args.subject_commit
            or run.get("event") != args.event_name
            or run.get("workflow_id") != args.producer_workflow_id
            or run.get("path") != expected_workflow_path
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
        ):
            raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH)
        artifact = _json(
            f"{base}/repos/{args.repository}/actions/artifacts/{args.artifact_id}", token
        )
        workflow_run = artifact.get("workflow_run")
        if (
            artifact.get("id") != args.artifact_id
            or artifact.get("name") != args.artifact_name
            or artifact.get("expired") is not False
            or not isinstance(workflow_run, dict)
            or workflow_run.get("id") != args.run_id
            or workflow_run.get("head_sha") != args.subject_commit
            or workflow_run.get("repository_id") != args.repository_id
        ):
            raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH)
        workflow_path = urllib.parse.quote(match.group("path"), safe="/")
        workflow = _json(
            f"{base}/repos/{args.repository}/contents/{workflow_path}?ref={match.group('sha')}",
            token,
        )
        if workflow.get("encoding") != "base64" or not isinstance(workflow.get("content"), str):
            raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH)
        try:
            workflow_bytes = base64.b64decode(workflow["content"], validate=True)
        except (ValueError, TypeError) as exc:
            raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH) from exc
        if hashlib.sha256(workflow_bytes).hexdigest() != args.producer_workflow_sha256:
            raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH)
        download_url = artifact.get("archive_download_url")
        if not isinstance(download_url, str) or not download_url.startswith(base + "/"):
            raise Helper1V61Error(Helper1FailureCode.NO_EXPLICIT_PRODUCER)
        artifact_bytes = _request(download_url, token, accept="application/octet-stream")
        artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()
        declared_digest = artifact.get("digest")
        if declared_digest != f"sha256:{artifact_digest}":
            raise Helper1V61Error(Helper1FailureCode.ARTIFACT_DIGEST_MISMATCH)
        _inventory, inventory_digest = inspect_approval_input_bytes(artifact_bytes)
        provenance = ApprovalInputProvenanceV2(
            repository_id=args.repository_id,
            repository_name=args.repository,
            subject_commit=args.subject_commit,
            subject_tree=args.subject_tree,
            producer_workflow_ref=args.producer_workflow_ref,
            producer_workflow_id=args.producer_workflow_id,
            producer_workflow_sha256=args.producer_workflow_sha256,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            event_name=args.event_name,
            artifact_id=args.artifact_id,
            artifact_name=args.artifact_name,
            artifact_sha256=artifact_digest,
            inventory_sha256=inventory_digest,
            canonical_subject_sha256=args.canonical_subject_sha256,
        )
        _write_new(args.output_artifact, artifact_bytes)
        _write_new(
            args.output_provenance,
            json.dumps(provenance.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n",
        )
    except (Helper1V61Error, OSError) as exc:
        code = exc.code.value if isinstance(exc, Helper1V61Error) else "NO_EXPLICIT_PRODUCER"
        print("HELPER1_APPROVAL_INPUT_FETCH_OK=0")
        print(f"ERROR_CODE={code}")
        return 1
    print("HELPER1_APPROVAL_INPUT_FETCH_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
