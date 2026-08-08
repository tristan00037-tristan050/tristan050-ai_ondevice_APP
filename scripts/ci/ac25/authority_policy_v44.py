"""Strict loader and source binding for externally provisioned AC-25 policy."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from . import strict_receipt as sr
from .v44_types import (
    AuthorityPolicyV2,
    AuthoritySource,
    AuthoritySourceObservation,
    CandidateBundleObservation,
    GuardInventoryItem,
    JUnitTestIdentity,
    TapTestIdentity,
)


POLICY_SCHEMA_VERSION = "butler.ac25.authority-policy.v2"


class AuthorityPolicyError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _exact(document, fields: Iterable[str]) -> None:
    expected = set(fields)
    if not isinstance(document, dict) or set(document) != expected:
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")


def _string(value, *, path: bool = False) -> str:
    if not isinstance(value, str) or not value or sr.CONTROL_RE.search(value):
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    if path:
        try:
            sr.validate_path(value)
        except sr.StrictReceiptError as exc:
            raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID") from exc
    return value


def _positive(value) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    return value


def _oid(value: str) -> str:
    if not isinstance(value, str) or sr.OID_RE.fullmatch(value) is None:
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    return value


def _digest(value: str) -> str:
    if not isinstance(value, str) or sr.SHA256_RE.fullmatch(value) is None:
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    return value


def _utc(value: str) -> str:
    if not isinstance(value, str) or sr.UTC_RE.fullmatch(value) is None:
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID") from exc
    return value


def _source(document) -> AuthoritySource:
    _exact(document, ("repository_id", "repository", "commit_sha", "tree_sha", "path", "blob_oid"))
    return AuthoritySource(
        repository_id=_positive(document["repository_id"]),
        repository=_string(document["repository"]),
        commit_sha=_oid(document["commit_sha"]),
        tree_sha=_oid(document["tree_sha"]),
        path=_string(document["path"], path=True),
        blob_oid=_oid(document["blob_oid"]),
    )


def load_authority_policy(raw: bytes) -> AuthorityPolicyV2:
    if not raw:
        raise AuthorityPolicyError("AUTHORITY_POLICY_NOT_PROVISIONED")
    try:
        document = sr.loads_strict(raw)
    except sr.StrictReceiptError as exc:
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID") from exc
    if sr.canonical_json_bytes(document) != raw:
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    fields = (
        "schema_version", "policy_id", "repository_id", "repository", "pr_number",
        "approved_start_head", "approved_start_tree", "approved_candidate_head",
        "approved_candidate_tree", "approved_changed_paths_sha256", "guard_inventory",
        "junit_inventory", "tap_inventory", "required_artifact_logical_ids",
        "candidate_workflow_paths", "authority_workflow_repository_id",
        "authority_workflow_path", "authority_workflow_commit",
        "authority_workflow_blob_oid", "issuer", "issued_at", "expires_at", "source",
    )
    _exact(document, fields)
    if document["schema_version"] != POLICY_SCHEMA_VERSION:
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")

    guards = []
    if not isinstance(document["guard_inventory"], list):
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    for item in document["guard_inventory"]:
        _exact(item, ("ordinal", "key"))
        ordinal = item["ordinal"]
        key = item["key"]
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
            raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
        if not isinstance(key, str) or not key.endswith("_OK"):
            raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
        guards.append(GuardInventoryItem(ordinal, key))
    if tuple(item.ordinal for item in guards) != tuple(range(len(guards))):
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")

    junit = []
    if not isinstance(document["junit_inventory"], list):
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    for item in document["junit_inventory"]:
        _exact(item, ("artifact_logical_id", "shard_id", "xml_path", "classname", "name"))
        junit.append(JUnitTestIdentity(
            _string(item["artifact_logical_id"]), _string(item["shard_id"]),
            _string(item["xml_path"], path=True), _string(item["classname"]), _string(item["name"]),
        ))

    tap = []
    if not isinstance(document["tap_inventory"], list):
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    for item in document["tap_inventory"]:
        _exact(item, ("artifact_logical_id", "shard_id", "tap_path", "subtest_path", "number", "name"))
        if not isinstance(item["subtest_path"], list):
            raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
        tap.append(TapTestIdentity(
            _string(item["artifact_logical_id"]), _string(item["shard_id"]),
            _string(item["tap_path"], path=True), tuple(_string(part) for part in item["subtest_path"]),
            _positive(item["number"]), _string(item["name"]),
        ))

    logical_ids = document["required_artifact_logical_ids"]
    workflow_paths = document["candidate_workflow_paths"]
    if not isinstance(logical_ids, list) or not isinstance(workflow_paths, list):
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")
    logical_tuple = tuple(_string(item) for item in logical_ids)
    workflow_tuple = tuple(_string(item, path=True) for item in workflow_paths)
    if len(logical_tuple) != len(set(logical_tuple)) or len(workflow_tuple) != len(set(workflow_tuple)):
        raise AuthorityPolicyError("AUTHORITY_POLICY_SCHEMA_INVALID")

    return AuthorityPolicyV2(
        schema_version=POLICY_SCHEMA_VERSION,
        policy_id=_string(document["policy_id"]),
        repository_id=_positive(document["repository_id"]),
        repository=_string(document["repository"]),
        pr_number=_positive(document["pr_number"]),
        approved_start_head=_oid(document["approved_start_head"]),
        approved_start_tree=_oid(document["approved_start_tree"]),
        approved_candidate_head=_oid(document["approved_candidate_head"]),
        approved_candidate_tree=_oid(document["approved_candidate_tree"]),
        approved_changed_paths_sha256=_digest(document["approved_changed_paths_sha256"]),
        guard_inventory=tuple(guards), junit_inventory=tuple(junit), tap_inventory=tuple(tap),
        required_artifact_logical_ids=logical_tuple,
        candidate_workflow_paths=workflow_tuple,
        authority_workflow_repository_id=_positive(document["authority_workflow_repository_id"]),
        authority_workflow_path=_string(document["authority_workflow_path"], path=True),
        authority_workflow_commit=_oid(document["authority_workflow_commit"]),
        authority_workflow_blob_oid=_oid(document["authority_workflow_blob_oid"]),
        issuer=_string(document["issuer"]), issued_at=_utc(document["issued_at"]),
        expires_at=_utc(document["expires_at"]), source=_source(document["source"]),
    )


def validate_policy_binding(
    policy: AuthorityPolicyV2,
    raw: bytes,
    source: AuthoritySourceObservation,
    candidate: CandidateBundleObservation,
    now_utc: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    failures: list[str] = []
    offending: list[str] = []
    if source.candidate_controlled:
        failures.append("AUTHORITY_POLICY_SELF_AUTHORED")
    if not source.protected:
        failures.append("AUTHORITY_POLICY_SOURCE_UNTRUSTED")
    if source.source != policy.source:
        failures.append("AUTHORITY_POLICY_SOURCE_UNTRUSTED")
    if source.bytes_sha256 != sr.sha256_bytes(raw):
        failures.append("AUTHORITY_POLICY_DIGEST_MISMATCH")
    coordinates = (
        policy.repository_id == candidate.repository_id,
        policy.repository == candidate.repository,
        policy.pr_number == candidate.pr_number,
        policy.approved_start_head == candidate.start_head,
        policy.approved_start_tree == candidate.start_tree,
        policy.approved_candidate_head == candidate.candidate_head,
        policy.approved_candidate_tree == candidate.candidate_tree,
        policy.approved_changed_paths_sha256 == candidate.changed_paths_sha256,
    )
    if not all(coordinates):
        failures.append("AUTHORITY_POLICY_COORDINATE_MISMATCH")
    try:
        now = datetime.strptime(_utc(now_utc), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        issued = datetime.strptime(policy.issued_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        expires = datetime.strptime(policy.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except AuthorityPolicyError:
        failures.append("AUTHORITY_POLICY_SCHEMA_INVALID")
    else:
        if issued > now or expires <= now or issued >= expires:
            failures.append("AUTHORITY_POLICY_EXPIRED")
    if not policy.guard_inventory:
        failures.append("GUARD_INVENTORY_EMPTY")
    if not policy.junit_inventory:
        failures.append("JUNIT_ZERO_TESTS")
    if not policy.tap_inventory:
        failures.append("TAP_ZERO_TESTS")
    if not policy.required_artifact_logical_ids:
        failures.append("ARTIFACT_PROVENANCE_AMBIGUOUS")
    for item in failures:
        if item not in offending:
            offending.append(item)
    return tuple(dict.fromkeys(failures)), tuple(offending)
