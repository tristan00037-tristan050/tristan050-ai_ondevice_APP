#!/usr/bin/env python3
"""Strict, side-effect-free Helper1 product subject selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
WORKFLOW_REF = re.compile(r"^[A-Za-z0-9_.@/-]{1,512}$")
PR_ACTIONS = frozenset({"opened", "reopened", "synchronize", "ready_for_review"})
SUPPORTED_EVENTS = frozenset({"pull_request", "merge_group", "push", "workflow_dispatch"})


class SubjectError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalSubject:
    event_name: str
    event_action: str | None
    repository_id: int
    repository_full_name: str
    subject_repository_full_name: str
    subject_sha: str
    pull_request_number: int | None
    merge_group_head_ref: str | None
    protected_ref: str | None
    workflow_ref: str
    workflow_sha: str
    approval_eligible: bool
    schema_version: str = "butler.helper1.canonical-subject.v1"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict())).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def strict_load(path: Path) -> Mapping[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SubjectError("BLOCK_EVENT_SCHEMA")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_bytes(),
            object_pairs_hook=unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                SubjectError("BLOCK_EVENT_SCHEMA")
            ),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise SubjectError("BLOCK_EVENT_SCHEMA") from error
    return _mapping(value, "BLOCK_EVENT_SCHEMA")


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SubjectError(code)
    return value


def _string(value: Any, code: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise SubjectError(code)
    return value


def _sha(value: Any) -> str:
    value = _string(value, "BLOCK_SUBJECT_SHA_MISMATCH", maximum=40)
    if SHA40.fullmatch(value) is None or value == "0" * 40:
        raise SubjectError("BLOCK_SUBJECT_SHA_MISMATCH")
    return value


def _repository(value: Any, code: str) -> str:
    value = _string(value, code, maximum=200)
    if REPOSITORY.fullmatch(value) is None:
        raise SubjectError(code)
    return value


def _positive_integer(value: Any, code: str) -> int:
    if type(value) is not int or value < 1:
        raise SubjectError(code)
    return value


def canonical_subject(
    event_name: str,
    event: Mapping[str, Any],
    *,
    expected_repository_id: int,
    expected_repository_full_name: str,
    workflow_ref: str,
    workflow_sha: str,
    protected_branches: frozenset[str] = frozenset({"main"}),
    dispatch_sha: str | None = None,
) -> CanonicalSubject:
    if event_name not in SUPPORTED_EVENTS:
        raise SubjectError("BLOCK_EVENT_UNSUPPORTED")
    event = _mapping(event, "BLOCK_EVENT_SCHEMA")
    repository = _mapping(event.get("repository"), "BLOCK_REPOSITORY_MISMATCH")
    repository_id = _positive_integer(repository.get("id"), "BLOCK_REPOSITORY_MISMATCH")
    repository_name = _repository(
        repository.get("full_name"), "BLOCK_REPOSITORY_MISMATCH"
    )
    if repository_id != expected_repository_id or repository_name != expected_repository_full_name:
        raise SubjectError("BLOCK_REPOSITORY_MISMATCH")
    if WORKFLOW_REF.fullmatch(workflow_ref) is None:
        raise SubjectError("BLOCK_WORKFLOW_PROVENANCE")
    workflow_sha = _sha(workflow_sha)

    action: str | None = None
    pull_number: int | None = None
    merge_ref: str | None = None
    protected_ref: str | None = None

    if event_name == "pull_request":
        action = _string(event.get("action"), "BLOCK_EVENT_SCHEMA", maximum=64)
        pull = _mapping(event.get("pull_request"), "BLOCK_EVENT_SCHEMA")
        pull_number = _positive_integer(event.get("number"), "BLOCK_EVENT_SCHEMA")
        head = _mapping(pull.get("head"), "BLOCK_EVENT_SCHEMA")
        head_repository = _mapping(head.get("repo"), "BLOCK_REPOSITORY_MISMATCH")
        subject_repository = _repository(
            head_repository.get("full_name"), "BLOCK_REPOSITORY_MISMATCH"
        )
        subject_sha = _sha(head.get("sha"))
        approval_eligible = action in PR_ACTIONS
    elif event_name == "merge_group":
        action = _string(event.get("action"), "BLOCK_EVENT_SCHEMA", maximum=64)
        group = _mapping(event.get("merge_group"), "BLOCK_EVENT_SCHEMA")
        subject_repository = repository_name
        subject_sha = _sha(group.get("head_sha"))
        merge_ref = _string(group.get("head_ref"), "BLOCK_EVENT_SCHEMA")
        approval_eligible = action == "checks_requested"
    elif event_name == "push":
        if type(event.get("deleted", False)) is not bool or event.get("deleted", False):
            raise SubjectError("BLOCK_EVENT_UNSUPPORTED")
        protected_ref = _string(event.get("ref"), "BLOCK_EVENT_SCHEMA")
        branch = protected_ref.removeprefix("refs/heads/")
        if protected_ref != f"refs/heads/{branch}" or branch not in protected_branches:
            raise SubjectError("BLOCK_EVENT_UNSUPPORTED")
        action = "push"
        subject_repository = repository_name
        subject_sha = _sha(event.get("after"))
        approval_eligible = True
    else:
        action = "workflow_dispatch"
        subject_repository = repository_name
        subject_sha = _sha(dispatch_sha)
        ref_value = event.get("ref")
        protected_ref = None if ref_value is None else _string(ref_value, "BLOCK_EVENT_SCHEMA")
        approval_eligible = False

    return CanonicalSubject(
        event_name=event_name,
        event_action=action,
        repository_id=repository_id,
        repository_full_name=repository_name,
        subject_repository_full_name=subject_repository,
        subject_sha=subject_sha,
        pull_request_number=pull_number,
        merge_group_head_ref=merge_ref,
        protected_ref=protected_ref,
        workflow_ref=workflow_ref,
        workflow_sha=workflow_sha,
        approval_eligible=approval_eligible,
    )


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--dispatch-sha")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--github-output", type=Path)
    arguments = parser.parse_args()
    try:
        subject = canonical_subject(
            arguments.event_name,
            strict_load(arguments.event),
            expected_repository_id=arguments.repository_id,
            expected_repository_full_name=arguments.repository,
            workflow_ref=arguments.workflow_ref,
            workflow_sha=arguments.workflow_sha,
            dispatch_sha=arguments.dispatch_sha,
        )
        _write(arguments.output, canonical_json(subject.to_dict()))
        if arguments.github_output is not None:
            with arguments.github_output.open("a", encoding="utf-8") as stream:
                stream.write(f"subject_sha={subject.subject_sha}\n")
                stream.write(f"subject_digest={subject.digest}\n")
                stream.write(f"approval_eligible={str(subject.approval_eligible).lower()}\n")
    except (OSError, SubjectError) as error:
        code = str(error)
        if not code.startswith("BLOCK_"):
            code = "BLOCK_EVENT_SCHEMA"
        print("CANONICAL_SUBJECT_OK=0")
        print(f"ERROR_CODE={code}")
        return 1
    print("CANONICAL_SUBJECT_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
