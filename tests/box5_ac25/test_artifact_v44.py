from __future__ import annotations

import io
import stat
import unicodedata
import zipfile
from dataclasses import replace

import pytest

from ac25.candidate_artifact_v44 import (
    ARTIFACT_PROVENANCE_AMBIGUOUS, CandidateArtifactError,
    _collect_pages, build_payload_manifest, resolve_exact_job_id,
)
from ac25.safe_zip_v44 import SafeZipReader
from ac25.strict_receipt import StrictReceiptError
from ac25.strict_v44 import validate_strict_receipt
from tests.box5_ac25.v44_fixtures import CANDIDATE_HEAD, REPOSITORY_ID, valid_input


def _archive(entries, *, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for item in entries:
            if len(item) == 2:
                name, raw = item
                mode = stat.S_IFREG | 0o600
            else:
                name, raw, mode = item
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = compression
            archive.writestr(info, raw)
    return buffer.getvalue()


def test_duplicate_artifact_candidates_rejected():
    original = valid_input()
    duplicate = original.candidate_bundle.artifacts + (original.candidate_bundle.artifacts[0],)
    candidate = replace(original.candidate_bundle, artifacts=duplicate)
    assert "ARTIFACT_PROVENANCE_AMBIGUOUS" in validate_strict_receipt(
        replace(original, candidate_bundle=candidate)
    ).failures


def test_stale_attempt_artifact_rejected():
    original = valid_input()
    first = original.candidate_bundle.artifacts[0]
    stale = replace(first, payload=replace(first.payload, run_attempt=2))
    candidate = replace(original.candidate_bundle, artifacts=(stale,) + original.candidate_bundle.artifacts[1:])
    assert "ARTIFACT_DIGEST_MISMATCH" in validate_strict_receipt(
        replace(original, candidate_bundle=candidate)
    ).failures


def test_payload_manifest_does_not_self_reference_artifact_digest():
    with pytest.raises(CandidateArtifactError, match=ARTIFACT_PROVENANCE_AMBIGUOUS):
        build_payload_manifest(
            logical_id="ac25-v44-python", repository_id=REPOSITORY_ID,
            head_sha=CANDIDATE_HEAD, run_id=1, run_attempt=1, job_id=1,
            job_name="job", files=(("payload-manifest.json", b"self"),),
        )


def test_artifact_locator_binds_exact_id_and_archive_digest():
    original = valid_input()
    first = original.candidate_bundle.artifacts[0]
    bad = replace(first, archive_sha256="0" * 64)
    candidate = replace(original.candidate_bundle, artifacts=(bad,) + original.candidate_bundle.artifacts[1:])
    assert "ARTIFACT_DIGEST_MISMATCH" in validate_strict_receipt(
        replace(original, candidate_bundle=candidate)
    ).failures


def test_junit_bytes_digest_must_bind_payload_file():
    original = valid_input()
    junit = replace(original.candidate_bundle.junit[0], source_sha256="0" * 64)
    candidate = replace(original.candidate_bundle, junit=(junit,))
    assert "JUNIT_IDENTITY_MISMATCH" in validate_strict_receipt(
        replace(original, candidate_bundle=candidate)
    ).failures


def test_tap_bytes_digest_must_bind_payload_file():
    original = valid_input()
    tap = replace(original.candidate_bundle.tap[0], source_sha256="0" * 64)
    candidate = replace(original.candidate_bundle, tap=(tap,))
    assert "TAP_IDENTITY_MISMATCH" in validate_strict_receipt(
        replace(original, candidate_bundle=candidate)
    ).failures


def test_duplicate_concrete_artifact_id_rejected():
    original = valid_input()
    first, second = original.candidate_bundle.artifacts
    duplicate = replace(second, locator=replace(second.locator, artifact_id=first.locator.artifact_id))
    candidate = replace(original.candidate_bundle, artifacts=(first, duplicate))
    assert "ARTIFACT_PROVENANCE_AMBIGUOUS" in validate_strict_receipt(
        replace(original, candidate_bundle=candidate)
    ).failures


def test_zip_traversal_rejected():
    with pytest.raises(StrictReceiptError, match="ARTIFACT_ARCHIVE_UNSAFE"):
        SafeZipReader().validate(_archive((("../escape", b"x"),)))


def test_zip_symlink_rejected():
    with pytest.raises(StrictReceiptError, match="ARTIFACT_ARCHIVE_UNSAFE"):
        SafeZipReader().validate(_archive((("link", b"target", stat.S_IFLNK | 0o777),)))


def test_zip_unicode_collision_rejected():
    nfd = unicodedata.normalize("NFD", "é.txt")
    with pytest.raises(StrictReceiptError, match="ARTIFACT_ARCHIVE_UNSAFE"):
        SafeZipReader().validate(_archive((("é.txt", b"a"), (nfd, b"b"))))


def test_zip_casefold_collision_rejected():
    with pytest.raises(StrictReceiptError, match="ARTIFACT_ARCHIVE_UNSAFE"):
        SafeZipReader().validate(_archive((("Proof.json", b"a"), ("proof.json", b"b"))))


def test_zip_bomb_limits_rejected():
    with pytest.raises(StrictReceiptError, match="ARTIFACT_ARCHIVE_UNSAFE"):
        SafeZipReader().validate(_archive((("bomb.bin", b"0" * 1024 * 1024),)))


def test_exact_artifact_id_digest_and_manifest_pass():
    verdict = validate_strict_receipt(valid_input())
    assert verdict.ok
    archive = SafeZipReader().validate(_archive((("proof.json", b"{}\n"),)))
    assert archive.read_exact("proof.json", max_bytes=16) == b"{}\n"


def test_job_id_resolution_requires_unique_exact_identity():
    pages = ({"jobs": [
        {"id": 1, "name": "job", "head_sha": CANDIDATE_HEAD},
        {"id": 2, "name": "other", "head_sha": CANDIDATE_HEAD},
    ]},)
    assert resolve_exact_job_id(pages, expected_job_name="job", expected_head_sha=CANDIDATE_HEAD) == 1


def test_job_id_resolution_rejects_ambiguous_identity():
    pages = ({"jobs": [
        {"id": 1, "name": "job", "head_sha": CANDIDATE_HEAD},
        {"id": 2, "name": "job", "head_sha": CANDIDATE_HEAD},
    ]},)
    with pytest.raises(CandidateArtifactError, match="ARTIFACT_JOB_ID_UNRESOLVED"):
        resolve_exact_job_id(pages, expected_job_name="job", expected_head_sha=CANDIDATE_HEAD)


def test_pagination_link_cannot_leave_github_api_origin():
    def requester(_url, _token):
        return {"jobs": []}, '<https://attacker.invalid/jobs?page=2>; rel="next"'

    with pytest.raises(CandidateArtifactError, match="ARTIFACT_JOB_ID_UNRESOLVED"):
        _collect_pages("https://api.github.com/repos/owner/repo/actions/jobs", "token", requester)
