"""Pure AC-25 v4.4 authority decision.

The function in this module performs no I/O, reads no environment variables,
and makes no network calls.  All candidate evidence remains untrusted until it
is matched against an externally provisioned policy and protected authority
workflow identity.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from .authority_policy_v44 import AuthorityPolicyError, load_authority_policy, validate_policy_binding
from .strict_receipt import SHA256_RE, UTC_RE, StrictReceiptError, canonical_json_bytes, sha256_bytes
from .v44_types import StrictValidationInput, StrictValidationVerdict


def _utc(value: str) -> datetime | None:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _payload_manifest_sha256(payload) -> str:
    document = asdict(payload)
    return sha256_bytes(canonical_json_bytes(document))


def validate_strict_receipt(inp: StrictValidationInput) -> StrictValidationVerdict:
    """Deterministic, no network, no file writes, no environment reads."""
    failures: list[str] = []
    offending: list[str] = []

    def fail(code: str, item: str | None = None) -> None:
        if code not in failures:
            failures.append(code)
        marker = item or code
        if marker not in offending:
            offending.append(marker)

    try:
        policy = load_authority_policy(inp.authority_policy_bytes)
    except AuthorityPolicyError as exc:
        fail(exc.code)
        return StrictValidationVerdict(False, tuple(failures), tuple(offending))

    policy_failures, policy_offending = validate_policy_binding(
        policy, inp.authority_policy_bytes, inp.authority_source,
        inp.candidate_bundle, inp.now_utc,
    )
    for index, code in enumerate(policy_failures):
        fail(code, policy_offending[index] if index < len(policy_offending) else code)

    # Guard identity is compared before any dict mapping.
    expected_guards = tuple((item.ordinal, item.key) for item in policy.guard_inventory)
    observed = inp.candidate_bundle.guard_items
    observed_guards = tuple((ordinal, key) for ordinal, key, _value in observed)
    expected_keys = tuple(key for _ordinal, key in expected_guards)
    observed_keys = tuple(key for _ordinal, key in observed_guards)
    if not expected_guards:
        fail("GUARD_INVENTORY_EMPTY")
    if len(expected_keys) != len(set(expected_keys)) or len(observed_keys) != len(set(observed_keys)):
        fail("GUARD_INVENTORY_DUPLICATE")
    expected_set = set(expected_keys)
    observed_set = set(observed_keys)
    if expected_set - observed_set:
        fail("GUARD_INVENTORY_MISSING")
    if observed_set - expected_set:
        fail("GUARD_INVENTORY_EXTRA")
    if expected_set == observed_set and observed_guards != expected_guards:
        fail("GUARD_INVENTORY_ORDER_MISMATCH")
    if any(value != "1" for _ordinal, _key, value in observed):
        fail("GUARD_VALUE_INVALID")

    artifact_ids = tuple(item.locator.logical_id for item in inp.candidate_bundle.artifacts)
    concrete_artifact_ids = tuple(item.locator.artifact_id for item in inp.candidate_bundle.artifacts)
    if len(artifact_ids) != len(set(artifact_ids)):
        fail("ARTIFACT_PROVENANCE_AMBIGUOUS")
    if (
        any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in concrete_artifact_ids)
        or len(concrete_artifact_ids) != len(set(concrete_artifact_ids))
    ):
        fail("ARTIFACT_PROVENANCE_AMBIGUOUS")
    if artifact_ids != policy.required_artifact_logical_ids:
        fail("ARTIFACT_PROVENANCE_AMBIGUOUS")
    remote_by_job = {(item.run_id, item.run_attempt, item.job_id): item for item in inp.remote}
    for artifact in inp.candidate_bundle.artifacts:
        locator = artifact.locator
        payload = artifact.payload
        if (
            payload.schema_version != "butler.ac25.payload-manifest.v1"
            or locator.logical_id != payload.logical_id
            or locator.workflow_run_id != payload.run_id
            or SHA256_RE.fullmatch(artifact.archive_sha256 or "") is None
            or artifact.archive_sha256 != locator.archive_sha256
            or locator.api_digest != "sha256:" + artifact.archive_sha256
            or locator.payload_manifest_sha256 != _payload_manifest_sha256(payload)
            or payload.repository_id != policy.repository_id
            or payload.head_sha != policy.approved_candidate_head
            or (payload.run_id, payload.run_attempt, payload.job_id) not in remote_by_job
        ):
            fail("ARTIFACT_DIGEST_MISMATCH", locator.logical_id)
            continue
        execution = remote_by_job[(payload.run_id, payload.run_attempt, payload.job_id)]
        if execution.job_name != payload.job_name or execution.head_sha != payload.head_sha:
            fail("ARTIFACT_PROVENANCE_AMBIGUOUS", locator.logical_id)
        file_paths = tuple(item.path for item in payload.files)
        if (
            not file_paths or len(file_paths) != len(set(file_paths))
            or any(
                item.byte_count < 0 or SHA256_RE.fullmatch(item.sha256 or "") is None
                for item in payload.files
            )
            or "payload-manifest.json" in file_paths
        ):
            fail("ARTIFACT_PROVENANCE_AMBIGUOUS", locator.logical_id)

    payload_files = {
        (artifact.payload.logical_id, item.path): item
        for artifact in inp.candidate_bundle.artifacts
        for item in artifact.payload.files
    }

    junit_identities = tuple(identity for item in inp.candidate_bundle.junit for identity in item.identities)
    expected_junit = policy.junit_inventory
    if not inp.candidate_bundle.junit:
        fail("JUNIT_REQUIRED_SHARD_MISSING")
    if not junit_identities or any(item.total <= 0 for item in inp.candidate_bundle.junit):
        fail("JUNIT_ZERO_TESTS")
    if len(junit_identities) != len(set(junit_identities)):
        fail("JUNIT_DUPLICATE_IDENTITY")
    if junit_identities != expected_junit:
        fail("JUNIT_IDENTITY_MISMATCH")
    if any(item.failures or item.errors or item.skipped for item in inp.candidate_bundle.junit):
        fail("JUNIT_IDENTITY_MISMATCH")
    for observation in inp.candidate_bundle.junit:
        coordinates = {
            (item.artifact_logical_id, item.xml_path) for item in observation.identities
        }
        if (
            len(coordinates) != 1
            or next(iter(coordinates), None) not in payload_files
            or payload_files[next(iter(coordinates))].sha256 != observation.source_sha256
        ):
            fail("JUNIT_IDENTITY_MISMATCH")

    tap_identities = tuple(identity for item in inp.candidate_bundle.tap for identity in item.identities)
    expected_tap = policy.tap_inventory
    if not inp.candidate_bundle.tap:
        fail("TAP_REQUIRED_SHARD_MISSING")
    if not tap_identities or any(item.planned <= 0 or item.seen <= 0 for item in inp.candidate_bundle.tap):
        fail("TAP_ZERO_TESTS")
    if len(tap_identities) != len(set(tap_identities)):
        fail("TAP_DUPLICATE_IDENTITY")
    if tap_identities != expected_tap:
        fail("TAP_IDENTITY_MISMATCH")
    if any(item.failed or item.skipped or item.todo or item.seen != item.planned for item in inp.candidate_bundle.tap):
        fail("TAP_IDENTITY_MISMATCH")
    for observation in inp.candidate_bundle.tap:
        coordinates = {
            (item.artifact_logical_id, item.tap_path) for item in observation.identities
        }
        if (
            len(coordinates) != 1
            or next(iter(coordinates), None) not in payload_files
            or payload_files[next(iter(coordinates))].sha256 != observation.source_sha256
        ):
            fail("TAP_IDENTITY_MISMATCH")

    if inp.required_set.pagination_complete is not True:
        fail("REMOTE_PAGINATION_INCOMPLETE")
    if inp.required_set.identities_complete is not True or (
        not inp.required_set.checks and not inp.required_set.workflows
    ):
        fail("REMOTE_REQUIRED_SET_UNKNOWN")

    authority_identity = (
        policy.authority_workflow_repository_id,
        policy.authority_workflow_path,
        policy.authority_workflow_commit,
        policy.authority_workflow_blob_oid,
    )
    authority_runs = [
        item for item in inp.remote
        if (item.repository_id, item.workflow_path, item.workflow_sha, item.workflow_blob_oid)
        == authority_identity
    ]
    if len(authority_runs) != 1:
        fail("AUTHORITY_WORKFLOW_NOT_PROVISIONED")
    else:
        if authority_runs[0].event != "workflow_dispatch" or authority_runs[0].head_sha != authority_runs[0].workflow_sha:
            fail("AUTHORITY_WORKFLOW_NOT_PROVISIONED")
        issued = _utc(policy.issued_at)
        authority_started = _utc(authority_runs[0].started_at)
        if issued is None or authority_started is None or issued > authority_started:
            fail("REMOTE_TIME_ORDER_INVALID")

    candidate_runs = [item for item in inp.remote if item not in authority_runs]
    if any(item.event != "pull_request" for item in candidate_runs):
        fail("REMOTE_SCHEMA_UNSUPPORTED")
    for path in policy.candidate_workflow_paths:
        matches = [item for item in candidate_runs if item.workflow_path == path]
        if not matches:
            fail("REMOTE_JOB_NOT_IN_ATTEMPT", path)
        for item in matches:
            if item.repository_id != policy.repository_id or item.head_sha != policy.approved_candidate_head:
                fail("REMOTE_HEAD_SHA_MISMATCH", path)
            if item.conclusion != "success":
                fail("REMOTE_CHECK_RUN_MISMATCH", path)
    if any(item.workflow_path not in policy.candidate_workflow_paths for item in candidate_runs):
        fail("REMOTE_SCHEMA_UNSUPPORTED")

    remote_checks = {(item.job_name, item.app_id) for item in candidate_runs}
    for check in inp.required_set.checks:
        if (check.context, check.app_id) not in remote_checks:
            fail("REMOTE_REQUIRED_SET_UNKNOWN", check.context)
    required_workflow_ids = {
        (item.repository_id, item.workflow_path, item.resolved_commit, item.resolved_blob_oid)
        for item in inp.required_set.workflows
    }
    if authority_identity in required_workflow_ids:
        required_workflow_ids.remove(authority_identity)
    candidate_workflow_ids = {
        (item.repository_id, item.workflow_path, item.workflow_sha, item.workflow_blob_oid)
        for item in candidate_runs
    }
    if not required_workflow_ids.issubset(candidate_workflow_ids):
        fail("REMOTE_REQUIRED_SET_UNKNOWN")

    if failures and not offending:
        failures.append("STRICT_VERDICT_CONTRACT_INVALID")
        offending.append("STRICT_VERDICT_CONTRACT_INVALID")
    return StrictValidationVerdict(not failures, tuple(failures), tuple(offending))


def require_authority_verdict(verdict: StrictValidationVerdict) -> None:
    """Receipt producers must call this immediately before any write."""
    if verdict.ok is True and verdict.failures == () and verdict.offending_items == ():
        return
    if verdict.ok is False and verdict.failures and verdict.offending_items:
        raise StrictReceiptError(verdict.failures[0])
    raise StrictReceiptError("STRICT_VERDICT_CONTRACT_INVALID")


__all__ = ["validate_strict_receipt", "require_authority_verdict"]
