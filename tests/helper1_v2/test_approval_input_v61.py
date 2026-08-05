from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile

import pytest

from butler_pc_core.helper1.approval_closure import KNOWN_ROLES, ROLE_MEDIA_TYPES
from butler_pc_core.helper1.approval_input import (
    APPROVAL_FILES,
    INVENTORY_NAME,
    LEGACY_FILES,
    ApprovalInputProvenanceV2,
    inspect_approval_input_bytes,
    verify_approval_input_bytes,
)
from butler_pc_core.helper1.failure_codes import Helper1FailureCode, Helper1V61Error

SHA40 = "1" * 40
TREE40 = "2" * 40
SHA256 = "3" * 64
WORKFLOW = f"owner/repo/.github/workflows/helper1-v2-approval-evidence.yml@{SHA40}"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _archive(*, omit: str | None = None, unsafe_name: str | None = None) -> bytes:
    files: dict[str, bytes] = {name: b"{}\n" for name in LEGACY_FILES}
    files.update({name: b"{}\n" for name in APPROVAL_FILES})
    object_raw = b"immutable approval object"
    files[f"objects/{hashlib.sha256(object_raw).hexdigest()}"] = object_raw
    if omit is not None:
        files.pop(omit)
    records: dict[str, object] = {}
    for name, raw in sorted(files.items()):
        role = None
        media_type = "application/json"
        if name.startswith("approval/"):
            role = name.rsplit("/", 1)[1].rsplit(".", 2)[0]
            media_type = (
                ROLE_MEDIA_TYPES[role]
                if name.endswith(".payload.json")
                else "application/vnd.butler.helper1.evidence-envelope+json;v=1"
            )
        records[name] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "media_type": media_type,
            "role": role,
        }
    files[INVENTORY_NAME] = _canonical(
        {"schema_version": "butler.helper1.approval-input-inventory.v2", "files": records}
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, raw)
        if unsafe_name is not None:
            archive.writestr(unsafe_name, b"bad")
    return stream.getvalue()


def _provenance(raw: bytes) -> ApprovalInputProvenanceV2:
    _inventory, inventory_digest = inspect_approval_input_bytes(raw)
    return ApprovalInputProvenanceV2(
        repository_id=7,
        repository_name="owner/repo",
        subject_commit=SHA40,
        subject_tree=TREE40,
        producer_workflow_ref=WORKFLOW,
        producer_workflow_id=17,
        producer_workflow_sha256=SHA256,
        run_id=11,
        run_attempt=2,
        event_name="workflow_dispatch",
        artifact_id=13,
        artifact_name="helper1-v2-approval-11-2",
        artifact_sha256=hashlib.sha256(raw).hexdigest(),
        inventory_sha256=inventory_digest,
        canonical_subject_sha256="4" * 64,
    )


def _verify(raw: bytes, provenance: ApprovalInputProvenanceV2):
    return verify_approval_input_bytes(
        raw,
        provenance,
        expected_repository_id=7,
        expected_repository_name="owner/repo",
        expected_subject_commit=SHA40,
        expected_subject_tree=TREE40,
        expected_run_id=11,
        expected_run_attempt=2,
        expected_workflow_ref=WORKFLOW,
        expected_workflow_id=17,
        expected_workflow_sha256=SHA256,
        expected_artifact_id=13,
        expected_artifact_name="helper1-v2-approval-11-2",
        expected_canonical_subject_sha256="4" * 64,
    )


def test_exact_legacy_and_seven_role_inventory_passes() -> None:
    raw = _archive()
    verified = _verify(raw, _provenance(raw))
    assert len(KNOWN_ROLES) == 7
    assert verified.provenance.artifact_sha256 == hashlib.sha256(raw).hexdigest()


def test_wrong_subject_and_artifact_digest_fail_closed() -> None:
    raw = _archive()
    provenance = _provenance(raw)
    with pytest.raises(Helper1V61Error) as subject_error:
        verify_approval_input_bytes(
            raw,
            provenance,
            expected_repository_id=7,
            expected_repository_name="owner/repo",
            expected_subject_commit="9" * 40,
            expected_subject_tree=TREE40,
            expected_run_id=11,
            expected_run_attempt=2,
            expected_workflow_ref=WORKFLOW,
            expected_workflow_id=17,
            expected_workflow_sha256=SHA256,
            expected_artifact_id=13,
            expected_artifact_name="helper1-v2-approval-11-2",
            expected_canonical_subject_sha256="4" * 64,
        )
    assert subject_error.value.code is Helper1FailureCode.PRODUCER_SUBJECT_MISMATCH
    with pytest.raises(Helper1V61Error) as digest_error:
        _verify(raw + b"changed", provenance)
    assert digest_error.value.code is Helper1FailureCode.ARTIFACT_DIGEST_MISMATCH


def test_self_selected_workflow_and_subject_digests_fail_closed() -> None:
    raw = _archive()
    provenance = _provenance(raw)
    with pytest.raises(Helper1V61Error) as workflow_error:
        verify_approval_input_bytes(
            raw,
            provenance,
            expected_repository_id=7,
            expected_repository_name="owner/repo",
            expected_subject_commit=SHA40,
            expected_subject_tree=TREE40,
            expected_run_id=11,
            expected_run_attempt=2,
            expected_workflow_ref=WORKFLOW,
            expected_workflow_id=17,
            expected_workflow_sha256="9" * 64,
            expected_artifact_id=13,
            expected_artifact_name="helper1-v2-approval-11-2",
            expected_canonical_subject_sha256="4" * 64,
        )
    assert workflow_error.value.code is Helper1FailureCode.PRODUCER_RUN_MISMATCH
    with pytest.raises(Helper1V61Error) as subject_error:
        verify_approval_input_bytes(
            raw,
            provenance,
            expected_repository_id=7,
            expected_repository_name="owner/repo",
            expected_subject_commit=SHA40,
            expected_subject_tree=TREE40,
            expected_run_id=11,
            expected_run_attempt=2,
            expected_workflow_ref=WORKFLOW,
            expected_workflow_id=17,
            expected_workflow_sha256=SHA256,
            expected_artifact_id=13,
            expected_artifact_name="helper1-v2-approval-11-2",
            expected_canonical_subject_sha256="8" * 64,
        )
    assert subject_error.value.code is Helper1FailureCode.PRODUCER_SUBJECT_MISMATCH


def test_missing_role_and_archive_traversal_fail_closed() -> None:
    with pytest.raises(Helper1V61Error) as missing:
        inspect_approval_input_bytes(_archive(omit=APPROVAL_FILES[0]))
    assert missing.value.code is Helper1FailureCode.INVENTORY_INCOMPLETE
    with pytest.raises(Helper1V61Error) as traversal:
        inspect_approval_input_bytes(_archive(unsafe_name="../escape"))
    assert traversal.value.code is Helper1FailureCode.UNSAFE_ARCHIVE
