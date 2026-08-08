"""Strict GitHub response binding for AC-25 v4.4.

Network collection is deliberately separate from the pure final validator.
This module validates already-collected response bodies and never guesses a
missing identity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence
from urllib.parse import urlparse

from .strict_receipt import OID_RE, UTC_RE, StrictReceiptError, validate_path
from .v44_types import (
    RemoteExecutionIdentity,
    RequiredCheckIdentity,
    RequiredSetObservation,
    RequiredWorkflowIdentity,
)


API_VERSION = "2026-03-10"
REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": API_VERSION,
    "User-Agent": "butler-ac25-authority-v4.4",
}


class RemoteError(StrictReceiptError):
    pass


def _fail(code: str):
    raise RemoteError(code)


def _positive(value, code="REMOTE_SCHEMA_UNSUPPORTED") -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _fail(code)
    return value


def _text(value, code="REMOTE_SCHEMA_UNSUPPORTED") -> str:
    if not isinstance(value, str) or not value:
        _fail(code)
    return value


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        _fail("REMOTE_SCHEMA_UNSUPPORTED")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail("REMOTE_SCHEMA_UNSUPPORTED")


def _oid(value: object, code="REMOTE_SCHEMA_UNSUPPORTED") -> str:
    if not isinstance(value, str) or OID_RE.fullmatch(value) is None:
        _fail(code)
    return value


def validate_remote_execution(
    *,
    repository_id: int,
    owner: str,
    repository: str,
    run: Mapping,
    attempt_jobs: Sequence[Mapping],
    check_run: Mapping,
    workflow: Mapping,
    workflow_commit: Mapping,
    workflow_blob: Mapping,
    expected_run_id: int,
    expected_attempt: int,
    expected_job_id: int,
    expected_check_run_id: int,
    expected_check_suite_id: int,
    expected_app_id: int,
    expected_head_sha: str,
    expected_workflow_blob_oid: str,
) -> RemoteExecutionIdentity:
    """Bind one exact run/attempt/job/check/workflow/Git-object tuple."""
    run_repository = run.get("repository")
    if (
        not isinstance(run_repository, Mapping)
        or _positive(run_repository.get("id")) != repository_id
        or run_repository.get("full_name") != f"{owner}/{repository}"
    ):
        _fail("REMOTE_SCHEMA_UNSUPPORTED")
    if _positive(run.get("id")) != expected_run_id or _positive(run.get("run_attempt")) != expected_attempt:
        _fail("REMOTE_RUN_ATTEMPT_MISMATCH")
    matches = [job for job in attempt_jobs if job.get("id") == expected_job_id]
    if not matches:
        _fail("REMOTE_JOB_NOT_IN_ATTEMPT")
    if len(matches) != 1:
        _fail("REMOTE_JOB_AMBIGUOUS")
    job = matches[0]
    check_url = _text(job.get("check_run_url"))
    parsed = urlparse(check_url)
    expected_prefix = f"/repos/{owner}/{repository}/check-runs/"
    if parsed.scheme != "https" or parsed.netloc != "api.github.com" or not parsed.path.startswith(expected_prefix):
        _fail("REMOTE_CHECK_RUN_MISMATCH")
    check_id = _positive(check_run.get("id"), "REMOTE_CHECK_RUN_MISMATCH")
    if check_id != expected_check_run_id or parsed.path != expected_prefix + str(check_id):
        _fail("REMOTE_CHECK_RUN_MISMATCH")
    suite = check_run.get("check_suite")
    app = check_run.get("app")
    if not isinstance(suite, Mapping) or _positive(suite.get("id"), "REMOTE_CHECK_SUITE_MISMATCH") != expected_check_suite_id:
        _fail("REMOTE_CHECK_SUITE_MISMATCH")
    if not isinstance(app, Mapping) or _positive(app.get("id"), "REMOTE_APP_ID_MISMATCH") != expected_app_id:
        _fail("REMOTE_APP_ID_MISMATCH")
    head_sha = _oid(run.get("head_sha"), "REMOTE_HEAD_SHA_MISMATCH")
    if head_sha != expected_head_sha or job.get("head_sha") != head_sha or check_run.get("head_sha") != head_sha:
        _fail("REMOTE_HEAD_SHA_MISMATCH")
    if check_run.get("name") != job.get("name") or check_run.get("conclusion") != job.get("conclusion"):
        _fail("REMOTE_CHECK_RUN_MISMATCH")
    workflow_id = _positive(run.get("workflow_id"))
    if _positive(workflow.get("id")) != workflow_id:
        _fail("REMOTE_SCHEMA_UNSUPPORTED")
    workflow_path = _text(workflow.get("path"))
    try:
        validate_path(workflow_path)
    except StrictReceiptError:
        _fail("REMOTE_SCHEMA_UNSUPPORTED")
    workflow_sha = _oid(run.get("workflow_sha"), "REMOTE_WORKFLOW_BLOB_MISMATCH")
    if _oid(workflow_commit.get("sha"), "REMOTE_WORKFLOW_BLOB_MISMATCH") != workflow_sha:
        _fail("REMOTE_WORKFLOW_BLOB_MISMATCH")
    tree = workflow_commit.get("tree")
    if not isinstance(tree, Mapping):
        _fail("REMOTE_WORKFLOW_BLOB_MISMATCH")
    blob_oid = _oid(workflow_blob.get("sha"), "REMOTE_WORKFLOW_BLOB_MISMATCH")
    if blob_oid != expected_workflow_blob_oid:
        _fail("REMOTE_WORKFLOW_BLOB_MISMATCH")
    if workflow_blob.get("encoding") not in ("base64", "utf-8"):
        _fail("REMOTE_WORKFLOW_BLOB_MISMATCH")
    run_start = _utc(run.get("run_started_at"))
    job_start = _utc(job.get("started_at"))
    job_end = _utc(job.get("completed_at"))
    check_start = _utc(check_run.get("started_at"))
    check_end = _utc(check_run.get("completed_at"))
    if not (run_start <= job_start <= job_end and run_start <= check_start <= check_end):
        _fail("REMOTE_TIME_ORDER_INVALID")
    if job.get("status") != "completed" or job.get("conclusion") != "success":
        _fail("REMOTE_CHECK_RUN_MISMATCH")
    return RemoteExecutionIdentity(
        repository_id=repository_id,
        workflow_id=workflow_id,
        workflow_path=workflow_path,
        workflow_sha=workflow_sha,
        workflow_blob_oid=blob_oid,
        run_id=expected_run_id,
        run_attempt=expected_attempt,
        job_id=expected_job_id,
        job_name=_text(job.get("name")),
        check_run_id=check_id,
        check_suite_id=_positive(suite.get("id")),
        app_id=_positive(app.get("id")),
        head_sha=head_sha,
        event=_text(run.get("event")),
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        conclusion=job.get("conclusion"),
    )


def build_required_set(
    *,
    branch_protection: Mapping,
    applied_rules: Sequence[Mapping],
    ruleset_summaries: Sequence[Mapping],
    ruleset_details: Sequence[Mapping],
    resolved_workflows: Sequence[RequiredWorkflowIdentity],
    pagination_complete: bool,
    includes_parents: bool,
) -> RequiredSetObservation:
    """Build the exact required set; unknown or unreadable rules fail closed."""
    if pagination_complete is not True or includes_parents is not True:
        _fail("REMOTE_PAGINATION_INCOMPLETE")
    contexts = branch_protection.get("contexts")
    checks_raw = branch_protection.get("checks")
    if not isinstance(contexts, list) or not isinstance(checks_raw, list):
        _fail("REMOTE_REQUIRED_SET_UNKNOWN")
    checks: list[RequiredCheckIdentity] = []
    for item in checks_raw:
        if not isinstance(item, Mapping):
            _fail("REMOTE_REQUIRED_SET_UNKNOWN")
        checks.append(RequiredCheckIdentity(_text(item.get("context")), _positive(item.get("app_id"))))
    for context in contexts:
        if not isinstance(context, str) or not context:
            _fail("REMOTE_REQUIRED_SET_UNKNOWN")
        if not any(item.context == context for item in checks):
            _fail("REMOTE_REQUIRED_SET_UNKNOWN")
    declared_workflows: list[tuple[int, str, str]] = []
    for rule in applied_rules:
        if not isinstance(rule, Mapping):
            _fail("REMOTE_SCHEMA_UNSUPPORTED")
        rule_type = rule.get("type")
        if rule_type not in ("required_status_checks", "workflows"):
            continue
        parameters = rule.get("parameters")
        if not isinstance(parameters, Mapping):
            _fail("REMOTE_REQUIRED_SET_UNKNOWN")
        if rule_type == "required_status_checks":
            required = parameters.get("required_status_checks")
            if not isinstance(required, list):
                _fail("REMOTE_REQUIRED_SET_UNKNOWN")
            for item in required:
                if not isinstance(item, Mapping):
                    _fail("REMOTE_REQUIRED_SET_UNKNOWN")
                identity = RequiredCheckIdentity(
                    _text(item.get("context")), _positive(item.get("integration_id")),
                )
                if identity not in checks:
                    checks.append(identity)
        else:
            workflows = parameters.get("workflows")
            if not isinstance(workflows, list) or not workflows:
                _fail("REMOTE_REQUIRED_SET_UNKNOWN")
            for item in workflows:
                if not isinstance(item, Mapping):
                    _fail("REMOTE_REQUIRED_SET_UNKNOWN")
                repository_id = _positive(item.get("repository_id"), "REMOTE_REQUIRED_SET_UNKNOWN")
                path = _text(item.get("path"), "REMOTE_REQUIRED_SET_UNKNOWN")
                ref = _text(item.get("ref"), "REMOTE_REQUIRED_SET_UNKNOWN")
                try:
                    validate_path(path)
                except StrictReceiptError:
                    _fail("REMOTE_REQUIRED_SET_UNKNOWN")
                declared_workflows.append((repository_id, path, ref))
    if len(checks) != len(set(checks)):
        _fail("REMOTE_REQUIRED_SET_UNKNOWN")
    required_workflow_rules = [
        rule for rule in applied_rules
        if isinstance(rule, Mapping) and rule.get("type") == "workflows"
    ]
    active_ids = {
        item.get("id") for item in ruleset_summaries
        if isinstance(item, Mapping) and item.get("enforcement") == "active"
    }
    detail_ids = {item.get("id") for item in ruleset_details if isinstance(item, Mapping)}
    if None in active_ids or not active_ids.issubset(detail_ids):
        _fail("REMOTE_REQUIRED_SET_UNKNOWN")
    if required_workflow_rules and not resolved_workflows:
        _fail("REMOTE_REQUIRED_SET_UNKNOWN")
    if len(resolved_workflows) != len(set(resolved_workflows)):
        _fail("REMOTE_REQUIRED_SET_UNKNOWN")
    for identity in resolved_workflows:
        if identity.repository_id <= 0 or not identity.ref:
            _fail("REMOTE_REQUIRED_SET_UNKNOWN")
        try:
            validate_path(identity.workflow_path)
        except StrictReceiptError:
            _fail("REMOTE_REQUIRED_SET_UNKNOWN")
        _oid(identity.resolved_commit, "REMOTE_REQUIRED_SET_UNKNOWN")
        _oid(identity.resolved_blob_oid, "REMOTE_REQUIRED_SET_UNKNOWN")
    resolved_coordinates = tuple(
        (item.repository_id, item.workflow_path, item.ref) for item in resolved_workflows
    )
    if tuple(declared_workflows) != resolved_coordinates:
        _fail("REMOTE_REQUIRED_SET_UNKNOWN")
    if not checks and not resolved_workflows:
        _fail("REMOTE_REQUIRED_SET_UNKNOWN")
    return RequiredSetObservation(
        checks=tuple(checks), workflows=tuple(resolved_workflows),
        pagination_complete=True, identities_complete=True,
    )


def exclude_authority_workflow_exact(
    workflows: Sequence[RequiredWorkflowIdentity], *, repository_id: int,
    path: str, commit: str, blob_oid: str,
) -> tuple[RequiredWorkflowIdentity, ...]:
    identity = (repository_id, path, commit, blob_oid)
    return tuple(
        item for item in workflows
        if (item.repository_id, item.workflow_path, item.resolved_commit, item.resolved_blob_oid) != identity
    )


__all__ = [
    "API_VERSION", "REQUEST_HEADERS", "RemoteError", "validate_remote_execution",
    "build_required_set", "exclude_authority_workflow_exact",
]
