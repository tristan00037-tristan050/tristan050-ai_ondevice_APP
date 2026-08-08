from __future__ import annotations

from dataclasses import asdict, replace

from ac25.strict_receipt import canonical_json_bytes, sha256_bytes
from ac25.v44_types import (
    ArtifactLocator,
    ArtifactObservation,
    AuthoritySource,
    AuthoritySourceObservation,
    CandidateBundleObservation,
    JUnitObservation,
    JUnitTestIdentity,
    PayloadFile,
    PayloadManifest,
    RemoteExecutionIdentity,
    RequiredCheckIdentity,
    RequiredSetObservation,
    RequiredWorkflowIdentity,
    StrictValidationInput,
    TapObservation,
    TapTestIdentity,
)


REPOSITORY_ID = 1097940756
REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
START_HEAD = "1" * 40
START_TREE = "2" * 40
CANDIDATE_HEAD = "3" * 40
CANDIDATE_TREE = "4" * 40
CHANGED = "5" * 64
AUTHORITY_REPOSITORY_ID = 777
AUTHORITY_COMMIT = "6" * 40
AUTHORITY_TREE = "7" * 40
AUTHORITY_BLOB = "8" * 40
POLICY_BLOB = "9" * 40
CANDIDATE_WORKFLOW = ".github/workflows/box5-ac25-stage-a-smoke.yml"
CANDIDATE_WORKFLOW_BLOB = "a" * 40
AUTHORITY_WORKFLOW = ".github/workflows/ac25-authority.yml"


def policy_document():
    return {
        "schema_version": "butler.ac25.authority-policy.v2",
        "policy_id": "ac25-r6-v44-test",
        "repository_id": REPOSITORY_ID,
        "repository": REPOSITORY,
        "pr_number": 904,
        "approved_start_head": START_HEAD,
        "approved_start_tree": START_TREE,
        "approved_candidate_head": CANDIDATE_HEAD,
        "approved_candidate_tree": CANDIDATE_TREE,
        "approved_changed_paths_sha256": CHANGED,
        "guard_inventory": [{"ordinal": 0, "key": "ONE_OK"}],
        "junit_inventory": [{
            "artifact_logical_id": "ac25-v44-python", "shard_id": "python",
            "xml_path": "junit.xml", "classname": "suite.Case", "name": "test_ok",
        }],
        "tap_inventory": [{
            "artifact_logical_id": "ac25-v44-node", "shard_id": "node",
            "tap_path": "publish.tap", "subtest_path": [], "number": 1,
            "name": "publishes safely",
        }],
        "required_artifact_logical_ids": ["ac25-v44-python", "ac25-v44-node"],
        "candidate_workflow_paths": [CANDIDATE_WORKFLOW],
        "authority_workflow_repository_id": AUTHORITY_REPOSITORY_ID,
        "authority_workflow_path": AUTHORITY_WORKFLOW,
        "authority_workflow_commit": AUTHORITY_COMMIT,
        "authority_workflow_blob_oid": AUTHORITY_BLOB,
        "issuer": "protected-control-plane",
        "issued_at": "2026-08-08T00:00:00Z",
        "expires_at": "2026-08-09T00:00:00Z",
        "source": {
            "repository_id": AUTHORITY_REPOSITORY_ID,
            "repository": "control/authority",
            "commit_sha": AUTHORITY_COMMIT,
            "tree_sha": AUTHORITY_TREE,
            "path": "policies/ac25-v44.json",
            "blob_oid": POLICY_BLOB,
        },
    }


def _remote(*, job_id: int, job_name: str) -> RemoteExecutionIdentity:
    return RemoteExecutionIdentity(
        repository_id=REPOSITORY_ID, workflow_id=100,
        workflow_path=CANDIDATE_WORKFLOW, workflow_sha=CANDIDATE_HEAD,
        workflow_blob_oid=CANDIDATE_WORKFLOW_BLOB,
        run_id=200, run_attempt=1, job_id=job_id, job_name=job_name,
        check_run_id=job_id + 1000, check_suite_id=500, app_id=15368,
        head_sha=CANDIDATE_HEAD, event="pull_request",
        started_at="2026-08-08T00:00:01Z", completed_at="2026-08-08T00:01:00Z",
        conclusion="success",
    )


def _artifact(
    logical_id: str, job_id: int, job_name: str, file_path: str, file_digest: str,
) -> ArtifactObservation:
    file = PayloadFile(file_path, file_digest, 10)
    payload = PayloadManifest(
        "butler.ac25.payload-manifest.v1", logical_id, REPOSITORY_ID,
        CANDIDATE_HEAD, 200, 1, job_id, job_name, (file,),
    )
    manifest_digest = sha256_bytes(canonical_json_bytes(asdict(payload)))
    archive_digest = ("c" if job_id == 11 else "d") * 64
    locator = ArtifactLocator(
        logical_id, job_id + 10000, archive_digest, "sha256:" + archive_digest,
        200, "2026-08-08T00:01:01Z", "2026-08-22T00:01:01Z", manifest_digest,
    )
    return ArtifactObservation(locator, payload, archive_digest)


def valid_input(document=None) -> StrictValidationInput:
    document = policy_document() if document is None else document
    raw = canonical_json_bytes(document)
    source_dict = document["source"]
    source = AuthoritySource(
        source_dict["repository_id"], source_dict["repository"], source_dict["commit_sha"],
        source_dict["tree_sha"], source_dict["path"], source_dict["blob_oid"],
    )
    source_observation = AuthoritySourceObservation(source, sha256_bytes(raw), True, False)
    junit_identity = JUnitTestIdentity("ac25-v44-python", "python", "junit.xml", "suite.Case", "test_ok")
    tap_identity = TapTestIdentity("ac25-v44-node", "node", "publish.tap", (), 1, "publishes safely")
    junit = JUnitObservation(1, 0, 0, 0, (junit_identity,), "e" * 64)
    tap = TapObservation(1, 1, 0, 0, 0, (tap_identity,), "f" * 64)
    python = _remote(job_id=11, job_name="python-check")
    node = _remote(job_id=12, job_name="node-check")
    authority = RemoteExecutionIdentity(
        repository_id=AUTHORITY_REPOSITORY_ID, workflow_id=300,
        workflow_path=AUTHORITY_WORKFLOW, workflow_sha=AUTHORITY_COMMIT,
        workflow_blob_oid=AUTHORITY_BLOB, run_id=400, run_attempt=1,
        job_id=401, job_name="authority-check", check_run_id=1401,
        check_suite_id=1500, app_id=15368, head_sha=AUTHORITY_COMMIT,
        event="workflow_dispatch", started_at="2026-08-08T00:00:01Z",
        completed_at="2026-08-08T00:02:00Z", conclusion="success",
    )
    candidate = CandidateBundleObservation(
        REPOSITORY_ID, REPOSITORY, 904, START_HEAD, START_TREE,
        CANDIDATE_HEAD, CANDIDATE_TREE, CHANGED, ((0, "ONE_OK", "1"),),
        (junit,), (tap,),
        (_artifact("ac25-v44-python", 11, "python-check", "junit.xml", "e" * 64),
         _artifact("ac25-v44-node", 12, "node-check", "publish.tap", "f" * 64)),
    )
    required = RequiredSetObservation(
        checks=(RequiredCheckIdentity("python-check", 15368),),
        workflows=(RequiredWorkflowIdentity(
            REPOSITORY_ID, CANDIDATE_WORKFLOW, "refs/heads/main",
            CANDIDATE_HEAD, CANDIDATE_WORKFLOW_BLOB,
        ),),
        pagination_complete=True, identities_complete=True,
    )
    return StrictValidationInput(raw, source_observation, candidate, (python, node, authority), required, "2026-08-08T12:00:00Z")
