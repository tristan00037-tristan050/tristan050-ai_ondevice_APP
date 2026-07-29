#!/usr/bin/env python3
"""Bind a FirstScreen evidence artifact to one successful producer run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Protocol

API_ROOT = "https://api.github.com"
EXPECTED_EVENT = "pull_request"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
READ_CHUNK = 1024 * 1024


class RunError(RuntimeError):
    pass


def _reject_constant(_: str) -> None:
    raise RunError("JSON_CONSTANT_INVALID")


def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in rows:
        if key in result:
            raise RunError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _strict_json(raw: bytes) -> Any:
    if len(raw) > MAX_JSON_BYTES or raw.startswith(b"\xef\xbb\xbf"):
        raise RunError("JSON_SIZE_OR_BOM_INVALID")
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunError("JSON_INVALID") from exc


def _oid(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is None:
        raise RunError("GIT_OID_INVALID")
    return ("sha1" if len(value) == 40 else "sha256", value)


def _positive_int(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RunError(code)
    return value


class Api(Protocol):
    def json(self, path: str) -> Mapping[str, Any]: ...

    def download(self, path: str, output: Path) -> str: ...


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        redirected = super().redirect_request(
            request,
            fp,
            code,
            message,
            headers,
            newurl,
        )
        if redirected is None:
            return None
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise RunError("ARTIFACT_REDIRECT_INVALID")
        if urllib.parse.urlsplit(request.full_url).netloc != parsed.netloc:
            redirected.remove_header("Authorization")
        return redirected


class GitHubApi:
    def __init__(self, token: str) -> None:
        if not token:
            raise RunError("GITHUB_TOKEN_MISSING")
        self._token = token
        self._opener = urllib.request.build_opener(
            _SafeRedirect(),
            urllib.request.HTTPSHandler(
                context=ssl.create_default_context(),
            ),
        )

    def _request(self, path: str) -> urllib.request.Request:
        if (
            not path.startswith("/")
            or "\n" in path
            or "\r" in path
            or path.startswith("//")
        ):
            raise RunError("API_PATH_INVALID")
        return urllib.request.Request(
            f"{API_ROOT}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "butler-firstscreen-trusted-verifier",
            },
        )

    def json(self, path: str) -> Mapping[str, Any]:
        try:
            with self._opener.open(self._request(path), timeout=30) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
        except (OSError, urllib.error.URLError) as exc:
            raise RunError("GITHUB_API_FAILED") from exc
        value = _strict_json(raw)
        if not isinstance(value, dict):
            raise RunError("GITHUB_API_RESPONSE_INVALID")
        return value

    def download(self, path: str, output: Path) -> str:
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        digest = hashlib.sha256()
        size = 0
        try:
            try:
                response = self._opener.open(self._request(path), timeout=60)
            except (OSError, urllib.error.URLError) as exc:
                raise RunError("ARTIFACT_DOWNLOAD_FAILED") from exc
            with response:
                while True:
                    chunk = response.read(READ_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_ARTIFACT_BYTES:
                        raise RunError("ARTIFACT_DOWNLOAD_TOO_LARGE")
                    digest.update(chunk)
                    view = memoryview(chunk)
                    while view:
                        written = os.write(descriptor, view)
                        if written <= 0:
                            raise RunError("ARTIFACT_WRITE_FAILED")
                        view = view[written:]
            if size < 1:
                raise RunError("ARTIFACT_DOWNLOAD_EMPTY")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return digest.hexdigest()


def resolve_run(
    event: Mapping[str, Any],
    api: Api,
    *,
    repository: str,
    workflow_name: str,
    workflow_path: str,
    artifact_prefix: str,
    artifact_output: Path,
    trusted_head: str,
    trusted_tree: str,
    trusted_workflow_ref: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = event.get("workflow_run")
    event_repository = event.get("repository")
    if (
        not isinstance(run, dict)
        or not isinstance(event_repository, dict)
        or event_repository.get("full_name") != repository
        or run.get("conclusion") != "success"
        or run.get("event") != EXPECTED_EVENT
        or run.get("name") != workflow_name
    ):
        raise RunError("UPSTREAM_RUN_INVALID")
    run_id = _positive_int(run.get("id"), "RUN_ID_INVALID")
    run_attempt = _positive_int(run.get("run_attempt"), "RUN_ATTEMPT_INVALID")
    workflow_id = _positive_int(run.get("workflow_id"), "WORKFLOW_ID_INVALID")
    _, head = _oid(run.get("head_sha"))
    trusted_algorithm, trusted_head_value = _oid(trusted_head)
    tree_algorithm, trusted_tree_value = _oid(trusted_tree)
    if trusted_algorithm != tree_algorithm:
        raise RunError("TRUSTED_OBJECT_FORMAT_MISMATCH")
    head_repository = run.get("head_repository")
    if not isinstance(head_repository, dict) or head_repository.get("full_name") != repository:
        raise RunError("FORK_ARTIFACT_NOT_ALLOWED")

    pull_requests = run.get("pull_requests")
    if not isinstance(pull_requests, list) or len(pull_requests) != 1:
        raise RunError("PULL_REQUEST_BINDING_INVALID")
    pull_request = pull_requests[0]
    if not isinstance(pull_request, dict):
        raise RunError("PULL_REQUEST_BINDING_INVALID")
    pr_number = _positive_int(pull_request.get("number"), "PULL_REQUEST_INVALID")
    pr = api.json(f"/repos/{repository}/pulls/{pr_number}")
    pr_head = pr.get("head")
    if (
        not isinstance(pr_head, dict)
        or pr_head.get("sha") != head
        or pr.get("number") != pr_number
    ):
        raise RunError("PULL_REQUEST_HEAD_MISMATCH")

    workflow = api.json(f"/repos/{repository}/actions/workflows/{workflow_id}")
    if (
        workflow.get("id") != workflow_id
        or workflow.get("name") != workflow_name
        or workflow.get("path") != workflow_path
        or workflow.get("state") != "active"
    ):
        raise RunError("PRODUCER_WORKFLOW_INVALID")

    commit = api.json(f"/repos/{repository}/git/commits/{head}")
    tree = commit.get("tree")
    if commit.get("sha") != head or not isinstance(tree, dict):
        raise RunError("SUBJECT_COMMIT_INVALID")
    object_format, tree_oid = _oid(tree.get("sha"))
    if len(head) != len(tree_oid):
        raise RunError("SUBJECT_OBJECT_FORMAT_MISMATCH")

    listing = api.json(f"/repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100")
    artifacts = listing.get("artifacts")
    total_count = listing.get("total_count")
    if (
        isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or not isinstance(artifacts, list)
        or total_count != len(artifacts)
    ):
        raise RunError("ARTIFACT_LIST_TRUNCATED_OR_INVALID")
    expected_name = f"{artifact_prefix}{head}"
    matches = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict)
        and artifact.get("name") == expected_name
        and artifact.get("expired") is False
    ]
    if len(matches) != 1:
        raise RunError("EVIDENCE_ARTIFACT_CARDINALITY_INVALID")
    artifact = matches[0]
    artifact_id = _positive_int(artifact.get("id"), "ARTIFACT_ID_INVALID")
    digest_match = re.fullmatch(
        r"sha256:([0-9a-f]{64})",
        str(artifact.get("digest") or ""),
    )
    if digest_match is None:
        raise RunError("ARTIFACT_DIGEST_MISSING")
    downloaded_digest = api.download(
        f"/repos/{repository}/actions/artifacts/{artifact_id}/zip",
        artifact_output,
    )
    if downloaded_digest != digest_match.group(1):
        raise RunError("ARTIFACT_DIGEST_MISMATCH")

    producer_ref = f"{repository}/{workflow_path}@refs/pull/{pr_number}/merge"
    metadata = {
        "schema_version": 1,
        "repository": repository,
        "event_name": EXPECTED_EVENT,
        "pull_request": pr_number,
        "subject_head": head,
        "tree_oid": {"algorithm": object_format, "hex": tree_oid},
        "producer": {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "workflow_path": workflow_path,
            "workflow_ref": producer_ref,
            "run_id": str(run_id),
            "run_attempt": run_attempt,
        },
        "artifact": {
            "id": artifact_id,
            "name": expected_name,
            "sha256": downloaded_digest,
        },
        "trusted_verifier": {
            "head": trusted_head_value,
            "tree": trusted_tree_value,
            "workflow_ref": trusted_workflow_ref,
        },
    }
    minimal_event = {
        "repository": {"full_name": repository},
        "pull_request": {
            "number": pr_number,
            "head": {"sha": head},
        },
    }
    return metadata, minimal_event


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        payload = (
            json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RunError("METADATA_WRITE_FAILED")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--artifact-prefix", required=True)
    parser.add_argument("--artifact-output", type=Path, required=True)
    parser.add_argument("--metadata-output", type=Path, required=True)
    parser.add_argument("--event-output", type=Path, required=True)
    parser.add_argument("--trusted-head", required=True)
    parser.add_argument("--trusted-tree", required=True)
    parser.add_argument("--trusted-workflow-ref", required=True)
    args = parser.parse_args()
    try:
        event_raw = args.event.read_bytes()
        event = _strict_json(event_raw)
        if not isinstance(event, dict):
            raise RunError("WORKFLOW_RUN_EVENT_INVALID")
        api = GitHubApi(os.environ.get("GITHUB_TOKEN", ""))
        metadata, minimal_event = resolve_run(
            event,
            api,
            repository=args.repository,
            workflow_name=args.workflow_name,
            workflow_path=args.workflow_path,
            artifact_prefix=args.artifact_prefix,
            artifact_output=args.artifact_output,
            trusted_head=args.trusted_head,
            trusted_tree=args.trusted_tree,
            trusted_workflow_ref=args.trusted_workflow_ref,
        )
        _write_json(args.metadata_output, metadata)
        _write_json(args.event_output, minimal_event)
    except (OSError, RunError, ValueError) as exc:
        code = str(exc) if re.fullmatch(r"[A-Z0-9_]+", str(exc)) else "TRUSTED_RUN_BINDING_FAILED"
        print("TRUSTED_RUN_BINDING_OK=0")
        print(f"ERROR_CODE={code}")
        return 1
    print("TRUSTED_RUN_BINDING_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
