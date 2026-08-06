#!/usr/bin/env python3
"""Protected Git subject resolution for Helper1 verdicts."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

GIT_OBJECT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
REPOSITORY_ID = 1097940756
WORKFLOW_PATH = ".github/workflows/helper1-v2-evidence.yml"
SUBJECT_KEYS = {
    "schema_version",
    "event_name",
    "event_action",
    "repository_id",
    "repository_full_name",
    "subject_repository_full_name",
    "subject_sha",
    "pull_request_number",
    "merge_group_head_ref",
    "protected_ref",
    "workflow_ref",
    "workflow_sha",
    "approval_eligible",
}


class SubjectBindingError(RuntimeError):
    pass


def _load(path: Path, code: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SubjectBindingError(code)
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_bytes(),
            object_pairs_hook=unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                SubjectBindingError(code)
            ),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise SubjectBindingError(code) from exc
    if type(value) is not dict:
        raise SubjectBindingError(code)
    return value


def _github_get(path: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "butler-helper1-protected-subject-verifier",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read(1024 * 1024))
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise SubjectBindingError("BLOCK_PR_HEAD_STALE") from exc
    if type(value) is not dict:
        raise SubjectBindingError("BLOCK_PR_HEAD_STALE")
    return value


def verify_canonical_subject(
    event_path: Path,
    subject_path: Path,
    *,
    api_get: Callable[[str], dict[str, Any]] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Cross-check untrusted subject data with protected workflow_run/API data."""
    event = _load(event_path, "BLOCK_EVENT_SCHEMA")
    subject = _load(subject_path, "BLOCK_EVENT_SCHEMA")
    run = event.get("workflow_run")
    repository = event.get("repository")
    if type(run) is not dict or type(repository) is not dict or set(subject) != SUBJECT_KEYS:
        raise SubjectBindingError("BLOCK_EVENT_SCHEMA")
    if (
        subject.get("schema_version") != "butler.helper1.canonical-subject.v1"
        or repository.get("id") != REPOSITORY_ID
        or repository.get("full_name") != REPOSITORY
        or subject.get("repository_id") != REPOSITORY_ID
        or subject.get("repository_full_name") != REPOSITORY
    ):
        raise SubjectBindingError("BLOCK_REPOSITORY_MISMATCH")
    event_name = run.get("event")
    subject_sha = subject.get("subject_sha")
    if (
        event_name not in {"pull_request", "merge_group", "push", "workflow_dispatch"}
        or subject.get("event_name") != event_name
        or type(subject_sha) is not str
        or GIT_OBJECT.fullmatch(subject_sha) is None
        or subject_sha == "0" * 40
        or run.get("head_sha") != subject_sha
    ):
        raise SubjectBindingError("BLOCK_SUBJECT_SHA_MISMATCH")
    workflow_ref = subject.get("workflow_ref")
    workflow_sha = subject.get("workflow_sha")
    if (
        run.get("name") != "helper1-v2-evidence-producer"
        or run.get("path") != WORKFLOW_PATH
        or run.get("conclusion") != "success"
        or type(run.get("id")) is not int
        or type(run.get("run_attempt")) is not int
        or type(workflow_ref) is not str
        or not workflow_ref.startswith(f"{REPOSITORY}/{WORKFLOW_PATH}@")
        or type(workflow_sha) is not str
        or GIT_OBJECT.fullmatch(workflow_sha) is None
    ):
        raise SubjectBindingError("BLOCK_WORKFLOW_PROVENANCE")

    if event_name == "pull_request":
        number = subject.get("pull_request_number")
        if type(number) is not int or number < 1 or subject.get("approval_eligible") is not True:
            raise SubjectBindingError("BLOCK_EVENT_SCHEMA")
        pull_requests = run.get("pull_requests")
        if type(pull_requests) is list and pull_requests:
            numbers = {
                item.get("number") for item in pull_requests if type(item) is dict
            }
            if number not in numbers:
                raise SubjectBindingError("BLOCK_PR_HEAD_STALE")
        if api_get is None:
            if not token:
                raise SubjectBindingError("BLOCK_PR_HEAD_STALE")
            api_get = lambda path: _github_get(path, token)
        current = api_get(f"/repos/{REPOSITORY}/pulls/{number}")
        head = current.get("head")
        head_repository = head.get("repo") if type(head) is dict else None
        if (
            type(head) is not dict
            or type(head_repository) is not dict
            or head.get("sha") != subject_sha
            or head_repository.get("full_name")
            != subject.get("subject_repository_full_name")
        ):
            raise SubjectBindingError("BLOCK_PR_HEAD_STALE")
    elif event_name == "merge_group":
        if (
            subject.get("subject_repository_full_name") != REPOSITORY
            or subject.get("approval_eligible") is not True
            or not str(subject.get("merge_group_head_ref", "")).startswith(
                "refs/heads/gh-readonly-queue/"
            )
        ):
            raise SubjectBindingError("BLOCK_EVENT_SCHEMA")
    elif event_name == "push":
        if (
            subject.get("subject_repository_full_name") != REPOSITORY
            or subject.get("protected_ref") != "refs/heads/main"
            or subject.get("approval_eligible") is not True
        ):
            raise SubjectBindingError("BLOCK_EVENT_UNSUPPORTED")
    elif subject.get("approval_eligible") is not False:
        raise SubjectBindingError("BLOCK_EVENT_UNSUPPORTED")
    return subject


def _run_git(repository_root: Path, arguments: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise SubjectBindingError("SUBJECT_COMMIT_OBJECT_UNAVAILABLE") from exc


def resolve_commit_tree(repository_root: Path, subject_commit: str) -> str:
    """Resolve ``commit^{tree}`` from the protected checkout object database.

    The repository path is supplied only by the protected verifier source. No
    evidence field, environment variable, or command-line option can redirect
    this lookup to an attacker-controlled repository.
    """
    if GIT_OBJECT.fullmatch(subject_commit) is None:
        raise SubjectBindingError("SUBJECT_COMMIT_OBJECT_INVALID")
    commit_type = _run_git(repository_root, ["cat-file", "-t", subject_commit])
    tree = _run_git(
        repository_root, ["rev-parse", "--verify", f"{subject_commit}^{{tree}}"]
    )
    if commit_type != "commit" or GIT_OBJECT.fullmatch(tree) is None:
        raise SubjectBindingError("SUBJECT_COMMIT_OBJECT_INVALID")
    return tree


def fetch_subject_object(
    repository_root: Path, event_path: Path, subject_path: Path | None = None
) -> str:
    """Fetch only the exact workflow subject object; never check it out."""
    try:
        event = json.loads(event_path.read_bytes())
        run = event["workflow_run"]
        repository = event["repository"]
        subject = (
            verify_canonical_subject(
                event_path,
                subject_path,
                token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"),
            )["subject_sha"]
            if subject_path is not None
            else run["head_sha"]
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SubjectBindingError("WORKFLOW_EVENT_INVALID") from exc
    if (
        type(event) is not dict
        or type(run) is not dict
        or type(repository) is not dict
        or repository.get("full_name") != "tristan00037-tristan050/tristan050-ai_ondevice_APP"
        or type(subject) is not str
        or GIT_OBJECT.fullmatch(subject) is None
    ):
        raise SubjectBindingError("WORKFLOW_EVENT_SUBJECT_INVALID")
    try:
        _run_git(
            repository_root,
            ["fetch", "--no-tags", "--depth=1", "origin", subject],
        )
    except SubjectBindingError:
        pull_requests = run.get("pull_requests")
        if type(pull_requests) is not list or len(pull_requests) != 1:
            raise SubjectBindingError("SUBJECT_COMMIT_OBJECT_UNAVAILABLE")
        pull = pull_requests[0]
        pull_number = pull.get("number") if type(pull) is dict else None
        if type(pull_number) is not int or pull_number < 1:
            raise SubjectBindingError("SUBJECT_PULL_REF_INVALID")
        _run_git(
            repository_root,
            [
                "fetch",
                "--no-tags",
                "--depth=1",
                "origin",
                f"refs/pull/{pull_number}/head",
            ],
        )
    observed = _run_git(repository_root, ["rev-parse", "--verify", "FETCH_HEAD^{commit}"])
    if observed != subject:
        raise SubjectBindingError("SUBJECT_FETCH_IDENTITY_MISMATCH")
    resolve_commit_tree(repository_root, subject)
    return subject


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-event", required=True, type=Path)
    parser.add_argument("--subject", type=Path)
    arguments = parser.parse_args()
    try:
        subject = fetch_subject_object(
            Path(__file__).resolve().parents[2],
            arguments.fetch_event,
            arguments.subject,
        )
    except SubjectBindingError as exc:
        print("SUBJECT_OBJECT_FETCHED=0")
        print(f"ERROR_CODE={exc}")
        return 1
    print("SUBJECT_OBJECT_FETCHED=1")
    print(f"SUBJECT_SHA={subject}")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
