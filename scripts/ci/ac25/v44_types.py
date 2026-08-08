"""Immutable data contracts for AC-25 R6 Close v4.4."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthoritySource:
    repository_id: int
    repository: str
    commit_sha: str
    tree_sha: str
    path: str
    blob_oid: str


@dataclass(frozen=True)
class AuthoritySourceObservation:
    source: AuthoritySource
    bytes_sha256: str
    protected: bool
    candidate_controlled: bool


@dataclass(frozen=True)
class GuardInventoryItem:
    ordinal: int
    key: str


@dataclass(frozen=True)
class JUnitTestIdentity:
    artifact_logical_id: str
    shard_id: str
    xml_path: str
    classname: str
    name: str


@dataclass(frozen=True)
class TapTestIdentity:
    artifact_logical_id: str
    shard_id: str
    tap_path: str
    subtest_path: tuple[str, ...]
    number: int
    name: str


@dataclass(frozen=True)
class AuthorityPolicyV2:
    schema_version: str
    policy_id: str
    repository_id: int
    repository: str
    pr_number: int
    approved_start_head: str
    approved_start_tree: str
    approved_candidate_head: str
    approved_candidate_tree: str
    approved_changed_paths_sha256: str
    guard_inventory: tuple[GuardInventoryItem, ...]
    junit_inventory: tuple[JUnitTestIdentity, ...]
    tap_inventory: tuple[TapTestIdentity, ...]
    required_artifact_logical_ids: tuple[str, ...]
    candidate_workflow_paths: tuple[str, ...]
    authority_workflow_repository_id: int
    authority_workflow_path: str
    authority_workflow_commit: str
    authority_workflow_blob_oid: str
    issuer: str
    issued_at: str
    expires_at: str
    source: AuthoritySource


@dataclass(frozen=True)
class JUnitObservation:
    total: int
    failures: int
    errors: int
    skipped: int
    identities: tuple[JUnitTestIdentity, ...]
    source_sha256: str


@dataclass(frozen=True)
class TapObservation:
    planned: int
    seen: int
    failed: int
    skipped: int
    todo: int
    identities: tuple[TapTestIdentity, ...]
    source_sha256: str


@dataclass(frozen=True)
class RemoteExecutionIdentity:
    repository_id: int
    workflow_id: int
    workflow_path: str
    workflow_sha: str
    workflow_blob_oid: str
    run_id: int
    run_attempt: int
    job_id: int
    job_name: str
    check_run_id: int
    check_suite_id: int
    app_id: int
    head_sha: str
    event: str
    started_at: str
    completed_at: str
    conclusion: str


@dataclass(frozen=True)
class RequiredCheckIdentity:
    context: str
    app_id: int


@dataclass(frozen=True)
class RequiredWorkflowIdentity:
    repository_id: int
    workflow_path: str
    ref: str
    resolved_commit: str
    resolved_blob_oid: str


@dataclass(frozen=True)
class RequiredSetObservation:
    checks: tuple[RequiredCheckIdentity, ...]
    workflows: tuple[RequiredWorkflowIdentity, ...]
    pagination_complete: bool
    identities_complete: bool


@dataclass(frozen=True)
class PayloadFile:
    path: str
    sha256: str
    byte_count: int


@dataclass(frozen=True)
class PayloadManifest:
    schema_version: str
    logical_id: str
    repository_id: int
    head_sha: str
    run_id: int
    run_attempt: int
    job_id: int
    job_name: str
    files: tuple[PayloadFile, ...]


@dataclass(frozen=True)
class ArtifactLocator:
    logical_id: str
    artifact_id: int
    archive_sha256: str
    api_digest: str
    workflow_run_id: int
    created_at: str
    expires_at: str
    payload_manifest_sha256: str


@dataclass(frozen=True)
class ArtifactObservation:
    locator: ArtifactLocator
    payload: PayloadManifest
    archive_sha256: str


@dataclass(frozen=True)
class CandidateBundleObservation:
    repository_id: int
    repository: str
    pr_number: int
    start_head: str
    start_tree: str
    candidate_head: str
    candidate_tree: str
    changed_paths_sha256: str
    guard_items: tuple[tuple[int, str, str], ...]
    junit: tuple[JUnitObservation, ...]
    tap: tuple[TapObservation, ...]
    artifacts: tuple[ArtifactObservation, ...]


@dataclass(frozen=True)
class StrictValidationInput:
    authority_policy_bytes: bytes
    authority_source: AuthoritySourceObservation
    candidate_bundle: CandidateBundleObservation
    remote: tuple[RemoteExecutionIdentity, ...]
    required_set: RequiredSetObservation
    now_utc: str


@dataclass(frozen=True)
class StrictValidationVerdict:
    ok: bool
    failures: tuple[str, ...]
    offending_items: tuple[str, ...]
