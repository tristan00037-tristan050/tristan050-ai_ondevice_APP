from __future__ import annotations

from copy import deepcopy

import pytest

from ac25.remote_v44 import (
    RemoteError, build_required_set, exclude_authority_workflow_exact,
    validate_remote_execution,
)
from ac25.v44_types import RequiredWorkflowIdentity


HEAD = "1" * 40
BLOB = "2" * 40


def _documents():
    run = {
        "id": 10, "run_attempt": 2, "workflow_id": 20, "head_sha": HEAD,
        "workflow_sha": HEAD, "event": "pull_request", "run_started_at": "2026-08-08T00:00:00Z",
        "repository": {"id": 99, "full_name": "owner/repo"},
    }
    job = {
        "id": 30, "name": "required-check", "head_sha": HEAD,
        "check_run_url": "https://api.github.com/repos/owner/repo/check-runs/40",
        "started_at": "2026-08-08T00:00:01Z", "completed_at": "2026-08-08T00:01:00Z",
        "status": "completed", "conclusion": "success",
    }
    check = {
        "id": 40, "name": "required-check", "head_sha": HEAD,
        "check_suite": {"id": 50}, "app": {"id": 60},
        "started_at": "2026-08-08T00:00:01Z", "completed_at": "2026-08-08T00:01:00Z",
        "conclusion": "success",
    }
    workflow = {"id": 20, "path": ".github/workflows/check.yml"}
    commit = {"sha": HEAD, "tree": {"sha": "3" * 40}}
    blob = {"sha": BLOB, "encoding": "base64", "content": ""}
    return run, [job], check, workflow, commit, blob


def _validate(documents=None, **overrides):
    run, jobs, check, workflow, commit, blob = documents or _documents()
    arguments = dict(
        repository_id=99, owner="owner", repository="repo", run=run,
        attempt_jobs=jobs, check_run=check, workflow=workflow,
        workflow_commit=commit, workflow_blob=blob, expected_run_id=10,
        expected_attempt=2, expected_job_id=30, expected_check_run_id=40,
        expected_check_suite_id=50, expected_app_id=60, expected_head_sha=HEAD,
        expected_workflow_blob_oid=BLOB,
    )
    arguments.update(overrides)
    return validate_remote_execution(**arguments)


def test_same_run_id_wrong_attempt_rejected():
    with pytest.raises(RemoteError, match="REMOTE_RUN_ATTEMPT_MISMATCH"):
        _validate(expected_attempt=3)


def test_job_not_in_attempt_rejected():
    with pytest.raises(RemoteError, match="REMOTE_JOB_NOT_IN_ATTEMPT"):
        _validate(expected_job_id=31)


def test_duplicate_job_in_attempt_rejected():
    documents = _documents()
    documents[1].append(deepcopy(documents[1][0]))
    with pytest.raises(RemoteError, match="REMOTE_JOB_AMBIGUOUS"):
        _validate(documents)


def test_wrong_check_run_rejected():
    with pytest.raises(RemoteError, match="REMOTE_CHECK_RUN_MISMATCH"):
        _validate(expected_check_run_id=41)


def test_wrong_check_suite_rejected():
    with pytest.raises(RemoteError, match="REMOTE_CHECK_SUITE_MISMATCH"):
        _validate(expected_check_suite_id=51)


def test_wrong_app_id_rejected():
    with pytest.raises(RemoteError, match="REMOTE_APP_ID_MISMATCH"):
        _validate(expected_app_id=61)


def test_wrong_workflow_blob_rejected():
    with pytest.raises(RemoteError, match="REMOTE_WORKFLOW_BLOB_MISMATCH"):
        _validate(expected_workflow_blob_oid="4" * 40)


def test_incomplete_pagination_rejected():
    with pytest.raises(RemoteError, match="REMOTE_PAGINATION_INCOMPLETE"):
        build_required_set(
            branch_protection={"contexts": [], "checks": []}, applied_rules=[],
            ruleset_summaries=[], ruleset_details=[], resolved_workflows=[],
            pagination_complete=False, includes_parents=True,
        )


def test_time_order_violation_rejected():
    documents = _documents()
    documents[1][0]["started_at"] = "2026-08-07T23:59:59Z"
    with pytest.raises(RemoteError, match="REMOTE_TIME_ORDER_INVALID"):
        _validate(documents)


def test_exact_run_attempt_job_check_tuple_passes():
    identity = _validate()
    assert (identity.run_id, identity.run_attempt, identity.job_id, identity.check_run_id) == (10, 2, 30, 40)


def test_run_repository_identity_must_match_endpoint():
    documents = _documents()
    documents[0]["repository"]["id"] = 100
    with pytest.raises(RemoteError, match="REMOTE_SCHEMA_UNSUPPORTED"):
        _validate(documents)


def test_applied_required_workflow_not_ignored():
    with pytest.raises(RemoteError, match="REMOTE_REQUIRED_SET_UNKNOWN"):
        build_required_set(
            branch_protection={"contexts": [], "checks": []},
            applied_rules=[{"type": "workflows"}],
            ruleset_summaries=[{"id": 1, "enforcement": "active"}],
            ruleset_details=[{"id": 1}], resolved_workflows=[],
            pagination_complete=True, includes_parents=True,
        )


def test_ruleset_parent_inclusion_required():
    with pytest.raises(RemoteError, match="REMOTE_PAGINATION_INCOMPLETE"):
        build_required_set(
            branch_protection={"contexts": ["required-check"], "checks": [{"context": "required-check", "app_id": 60}]},
            applied_rules=[], ruleset_summaries=[], ruleset_details=[], resolved_workflows=[],
            pagination_complete=True, includes_parents=False,
        )


def test_unreadable_required_workflow_identity_fails_unknown():
    with pytest.raises(RemoteError, match="REMOTE_REQUIRED_SET_UNKNOWN"):
        build_required_set(
            branch_protection={"contexts": [], "checks": []},
            applied_rules=[{"type": "workflows"}],
            ruleset_summaries=[{"id": 1, "enforcement": "active"}],
            ruleset_details=[], resolved_workflows=[], pagination_complete=True,
            includes_parents=True,
        )


def test_self_exclusion_is_exact_identity_only():
    exact = RequiredWorkflowIdentity(1, ".github/workflows/a.yml", "main", "1" * 40, "2" * 40)
    same_name_other_blob = RequiredWorkflowIdentity(1, ".github/workflows/a.yml", "main", "1" * 40, "3" * 40)
    result = exclude_authority_workflow_exact(
        (exact, same_name_other_blob), repository_id=1, path=exact.workflow_path,
        commit=exact.resolved_commit, blob_oid=exact.resolved_blob_oid,
    )
    assert result == (same_name_other_blob,)
