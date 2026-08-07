from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from butler_pc_core.helper1.test_evidence import CHECKS, LANES, CheckResult, LaneResult
import scripts.ci.helper1_producer_package as producer_package_module
from scripts.ci.helper1_producer_package import (
    PACKAGE_RELATIVE,
    ProducerPackageError,
    build_protected_bootstrap_package,
    load_verified_package,
    main as producer_package_main,
)
from scripts.ci.helper1_protected_bootstrap import (
    EXPECTED_CHECKS,
    EXPECTED_LANES,
    ProtectedBootstrapError,
    build_bootstrap_receipts,
    verify_untrusted_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/helper1_v2/fixtures/github-helper1-run-31063756134.v1.json"
POLICY = ROOT / "contracts/helper1/trusted-verifier-policy-v1.json"
WORKFLOW = ROOT / ".github/workflows/helper1-v2-evidence.yml"
SUBJECT_COMMIT = "2f7fe4b9fc8c2a126ce947ed121d764dc033cb7c"
SUBJECT_TREE = "ac0ce51d76cc08cb7aaa9a63728d1a1cae8f35b2"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _materialize_raw_artifact(root: Path) -> tuple[dict, dict]:
    root.mkdir(mode=0o700)
    evidence = root / "test-evidence"
    evidence.mkdir(mode=0o700)
    subject = {
        "approval_eligible": True,
        "event_action": "synchronize",
        "event_name": "pull_request",
        "merge_group_head_ref": None,
        "protected_ref": None,
        "pull_request_number": 902,
        "repository_full_name": "tristan00037-tristan050/tristan050-ai_ondevice_APP",
        "repository_id": 1097940756,
        "schema_version": "butler.helper1.canonical-subject.v1",
        "subject_repository_full_name": "tristan00037-tristan050/tristan050-ai_ondevice_APP",
        "subject_sha": SUBJECT_COMMIT,
        "workflow_ref": (
            "tristan00037-tristan050/tristan050-ai_ondevice_APP/"
            ".github/workflows/helper1-v2-evidence.yml@refs/pull/902/merge"
        ),
        "workflow_sha": "cf0ad90373c45aa61fe0a54b9a8b7b1cc1f4f9b2",
    }
    submission = {
        "canonical_subject_sha256": hashlib.sha256(_canonical(subject)).hexdigest(),
        "product_evidence_present": True,
        "run_id": "31063756134:1",
        "schema_version": "butler.helper1.untrusted-submission.v1",
        "subject_commit": SUBJECT_COMMIT,
    }
    raw_root = evidence / "raw"
    raw_root.mkdir(mode=0o700)
    lane_records = []
    for lane_id in sorted(EXPECTED_LANES):
        spec = LANES[lane_id]
        blocked = lane_id == "native-macos-helper1-v51"
        collected = 0 if blocked else spec.expected_collected
        assert collected is not None
        stdout_path = f"raw/{lane_id}.stdout.log"
        stderr_path = f"raw/{lane_id}.stderr.log"
        (evidence / stdout_path).write_bytes(b"PASS\n")
        (evidence / stderr_path).write_bytes(b"")
        if blocked:
            report_sha256 = None
        elif spec.report_kind == "junit":
            report_raw = (
                f'<testsuite tests="{collected}" failures="0" errors="0" skipped="0"/>'
            ).encode("ascii")
            (evidence / spec.report_name).write_bytes(report_raw)
            report_sha256 = hashlib.sha256(report_raw).hexdigest()
        else:
            report_raw = _canonical(
                {
                    "numFailedTests": 0,
                    "numPassedTests": collected,
                    "numPendingTests": 0,
                    "numTotalTests": collected,
                }
            )
            (evidence / spec.report_name).write_bytes(report_raw)
            report_sha256 = hashlib.sha256(report_raw).hexdigest()
        lane_records.append(
            LaneResult(
                schema_version="butler.helper1.test-run-record.v1",
                lane_id=lane_id,
                source_commit=SUBJECT_COMMIT,
                source_tree=SUBJECT_TREE,
                argv=spec.argv,
                cwd_rel=spec.cwd_rel,
                return_code=None if blocked else 0,
                runner_name="fixture",
                runner_version="1",
                environment_digest="sha256:" + "1" * 64,
                started_at_epoch_s=1,
                finished_at_epoch_s=2,
                stdout_sha256=hashlib.sha256(b"PASS\n").hexdigest(),
                stderr_sha256=EMPTY_SHA256,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                report_sha256=report_sha256,
                collected=collected,
                passed=collected,
                failed=0,
                errors=0,
                skipped=0,
                blocked=1 if blocked else 0,
                status="BLOCKED" if blocked else "PASSED",
                error_code="MACOS_NATIVE_LANE_NOT_CONFIGURED" if blocked else "NONE",
            ).to_dict()
        )
    check_records = []
    for check_id in sorted(EXPECTED_CHECKS):
        spec = CHECKS[check_id]
        stdout_path = f"raw/{check_id}.stdout.log"
        stderr_path = f"raw/{check_id}.stderr.log"
        (evidence / stdout_path).write_bytes(b"PASS\n")
        (evidence / stderr_path).write_bytes(b"")
        check_records.append(
            CheckResult(
                schema_version="butler.helper1.check-run-record.v1",
                check_id=check_id,
                source_commit=SUBJECT_COMMIT,
                source_tree=SUBJECT_TREE,
                argv=spec.argv,
                cwd_rel=spec.cwd_rel,
                return_code=0,
                started_at_epoch_s=1,
                finished_at_epoch_s=2,
                stdout_sha256=hashlib.sha256(b"PASS\n").hexdigest(),
                stderr_sha256=EMPTY_SHA256,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                status="PASSED",
                error_code="NONE",
            ).to_dict()
        )
    index = {
        "schema_version": "butler.helper1.test-evidence-index.v1",
        "source_tree": SUBJECT_TREE,
        "lanes": lane_records,
        "checks": check_records,
        "all_required_lanes_passed": False,
        "all_required_checks_passed": True,
        "required_lanes_blocked": 1,
    }
    (root / "CANONICAL_SUBJECT.json").write_bytes(_canonical(subject) + b"\n")
    (root / "SUBMISSION.json").write_bytes(_canonical(submission) + b"\n")
    (evidence / "TEST_EVIDENCE_INDEX.v1.json").write_bytes(_canonical(index) + b"\n")
    return subject, index


def _event(root: Path) -> Path:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    event = {
        "repository": {
            "id": 1097940756,
            "full_name": "tristan00037-tristan050/tristan050-ai_ondevice_APP",
        },
        "workflow_run": {
            **fixture["run"],
            "event": "pull_request",
        },
    }
    path = root / "event.json"
    path.write_bytes(_canonical(event) + b"\n")
    return path


def _transport(fixture: dict, artifact_root: Path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in artifact_root.rglob("*") if item.is_file()):
            name = path.relative_to(artifact_root).as_posix()
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = (0o100600) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    archive_raw = stream.getvalue()
    fixture["artifact"]["digest"] = "sha256:" + hashlib.sha256(archive_raw).hexdigest()
    fixture["artifact"]["size_in_bytes"] = len(archive_raw)
    workflow = {
        "encoding": "base64",
        "content": base64.b64encode(WORKFLOW.read_bytes()).decode("ascii"),
    }

    def request(url: str):
        if "/jobs?" in url:
            return {"total_count": 1, "jobs": [fixture["job"]]}
        if "/artifacts?" in url:
            return {"total_count": 1, "artifacts": [fixture["artifact"]]}
        if "/contents/" in url:
            return workflow
        if "/actions/runs/" in url:
            return fixture["run"]
        raise AssertionError(url)

    return request, lambda _url: archive_raw


def _policy() -> tuple[dict, bytes]:
    raw = POLICY.read_bytes()
    return json.loads(raw), raw


def test_clean_runner_executes_raw_to_package_to_unsigned_verdict(tmp_path: Path) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    request, request_archive = _transport(fixture, artifact_root)

    verified, descriptor = build_protected_bootstrap_package(
        artifact_root,
        event,
        request_json=request,
        request_archive=request_archive,
    )
    assert verified.artifact_id == 8953102850
    assert descriptor["subject_tree"] == SUBJECT_TREE
    package_path = artifact_root / PACKAGE_RELATIVE
    assert package_path.is_file()

    policy, policy_raw = _policy()
    loaded = load_verified_package(
        package_path,
        policy=policy,
        policy_raw=policy_raw,
        require_authority=False,
    )
    approval = json.loads(loaded.bootstrap_receipts["APPROVAL_RECEIPT.v1.json"])
    assert set(approval["approval_values"].values()) == {0}
    assert loaded.legacy_evidence == {}
    assert loaded.approval_files == {}

    verdict = tmp_path / "verdict.json"
    env = {**os.environ, "GITHUB_EVENT_PATH": str(event)}
    completed = subprocess.run(
        (
            sys.executable,
            "scripts/ci/helper1_trusted_verifier.py",
            "--event",
            str(event),
            "--producer-package",
            str(package_path),
            "--output",
            str(verdict),
        ),
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 1
    assert "CODE_PASS=0" in completed.stdout
    value = json.loads(verdict.read_text(encoding="utf-8"))
    assert value["error_code"] == "TRUST_POLICY_DISABLED"
    assert value["producer_package_sha256"] == "sha256:" + loaded.package_sha256
    assert value["search_quality_evidence_sha256"] == "sha256:" + hashlib.sha256(
        loaded.bootstrap_receipts["QUALITY_MEASUREMENT.v1.json"]
    ).hexdigest()


def test_actual_github_response_shape_and_failed_sibling_job_are_accepted(tmp_path: Path) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["artifact"]["digest"] == (
        "sha256:ed3535787e2dd23ac9d88bd36154d7efa60f5e84fd0343b347869073e3b96f30"
    )
    policy, _raw = _policy()
    request, request_archive = _transport(fixture, artifact_root)

    verified = verify_untrusted_artifact(
        artifact_root,
        event,
        policy,
        request_json=request,
        request_archive=request_archive,
    )
    assert fixture["run"]["conclusion"] == "failure"
    assert fixture["job"]["conclusion"] == "success"
    assert verified.producer_run == "31063756134:1"

    index_path = artifact_root / "test-evidence/TEST_EVIDENCE_INDEX.v1.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    declared = next(item for item in index["lanes"] if item["status"] == "PASSED")
    declared["passed"] -= 1
    declared["failed"] += 1
    index_path.write_bytes(_canonical(index) + b"\n")
    request, request_archive = _transport(fixture, artifact_root)
    with pytest.raises(ProtectedBootstrapError, match="UNTRUSTED_EVIDENCE_INVALID"):
        verify_untrusted_artifact(
            artifact_root,
            event,
            policy,
            request_json=request,
            request_archive=request_archive,
        )


def test_unsuccessful_untrusted_job_blocks_before_packaging(tmp_path: Path) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["job"]["conclusion"] = "failure"
    request, request_archive = _transport(fixture, artifact_root)

    with pytest.raises(ProtectedBootstrapError, match="UNTRUSTED_CANDIDATE_JOB_NOT_SUCCESSFUL"):
        verify_untrusted_artifact(
            artifact_root,
            event,
            _policy()[0],
            request_json=request,
            request_archive=request_archive,
        )


def test_workflow_byte_drift_blocks_before_packaging(tmp_path: Path) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    policy, _raw = _policy()
    policy["quality_producer_workflow_sha256"] = "sha256:" + "0" * 64
    request, request_archive = _transport(fixture, artifact_root)

    with pytest.raises(ProtectedBootstrapError, match="UNTRUSTED_WORKFLOW_IDENTITY_INVALID"):
        verify_untrusted_artifact(
            artifact_root,
            event,
            policy,
            request_json=request,
            request_archive=request_archive,
        )


def test_policy_workflow_fingerprints_must_match_at_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, _raw = _policy()
    policy["quality_producer_workflow_sha256"] = "sha256:" + "0" * 64
    divergent_policy = tmp_path / "policy.json"
    divergent_policy.write_bytes(_canonical(policy) + b"\n")

    monkeypatch.setattr(producer_package_module, "POLICY_PATH", divergent_policy)
    with pytest.raises(ProducerPackageError, match="PRODUCER_PACKAGE_POLICY_INVALID"):
        producer_package_module._policy()

    scripts_ci = str(ROOT / "scripts/ci")
    sys.path.insert(0, scripts_ci)
    try:
        from publish_helper1_subject_check import CheckPublishError, validate_policy

        with pytest.raises(CheckPublishError, match="TRUST_POLICY_INVALID"):
            validate_policy(policy)
    finally:
        sys.path.remove(scripts_ci)


def test_provenance_workflow_fingerprint_must_match_canonical_policy(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    request, request_archive = _transport(fixture, artifact_root)
    policy, _raw = _policy()
    verified = verify_untrusted_artifact(
        artifact_root,
        event,
        policy,
        request_json=request,
        request_archive=request_archive,
    )
    receipts = build_bootstrap_receipts(
        replace(verified, workflow_sha256="0" * 64),
        policy_enabled=False,
    )
    files = {
        "TEST_EVIDENCE/TEST_EVIDENCE_INDEX.v1.json": verified.test_index_raw,
        **{
            f"PROTECTED_BOOTSTRAP/{name}": raw
            for name, raw in receipts.items()
        },
    }
    manifest = {"release_eligible": False, "producer_run": verified.producer_run}

    with pytest.raises(ProducerPackageError, match="BOOTSTRAP_RECEIPT_BINDING_INVALID"):
        producer_package_module._verify_bootstrap_receipts(
            files,
            manifest,
            policy=policy,
            subject_commit=verified.subject["subject_sha"],
            subject_tree=verified.source_tree,
            producer_run=verified.producer_run,
        )


def test_current_workflow_fingerprint_reaches_unsigned_zero(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    request, request_archive = _transport(fixture, artifact_root)
    build_protected_bootstrap_package(
        artifact_root,
        event,
        request_json=request,
        request_archive=request_archive,
    )
    policy, policy_raw = _policy()
    loaded = load_verified_package(
        artifact_root / PACKAGE_RELATIVE,
        policy=policy,
        policy_raw=policy_raw,
        require_authority=False,
    )
    approval = json.loads(loaded.bootstrap_receipts["APPROVAL_RECEIPT.v1.json"])

    assert approval["state"] == "UNSIGNED_ZERO"
    assert approval["signature_b64"] is None
    assert set(approval["approval_values"].values()) == {0}


def test_workflow_fingerprint_is_not_duplicated_in_execution_code() -> None:
    workflow_sha256 = hashlib.sha256(WORKFLOW.read_bytes()).hexdigest()
    execution_sources = sorted((ROOT / "scripts/ci").rglob("*.py"))

    assert execution_sources
    assert all(
        workflow_sha256 not in path.read_text(encoding="utf-8")
        for path in execution_sources
    )
    producer_source = (
        ROOT / "scripts/ci/helper1_producer_package.py"
    ).read_text(encoding="utf-8")
    assert "APPROVAL_PRODUCER_WORKFLOW_SHA256" not in producer_source


def test_downloaded_archive_digest_mismatch_blocks_before_packaging(tmp_path: Path) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    request, request_archive = _transport(fixture, artifact_root)
    fixture["artifact"]["size_in_bytes"] += 1

    with pytest.raises(ProtectedBootstrapError, match="UNTRUSTED_ARTIFACT_DIGEST_MISMATCH"):
        verify_untrusted_artifact(
            artifact_root,
            event,
            _policy()[0],
            request_json=request,
            request_archive=request_archive,
        )

    fixture["artifact"]["size_in_bytes"] -= 1
    fixture["artifact"]["digest"] = "sha256:" + "0" * 64

    with pytest.raises(ProtectedBootstrapError, match="UNTRUSTED_ARTIFACT_DIGEST_MISMATCH"):
        verify_untrusted_artifact(
            artifact_root,
            event,
            _policy()[0],
            request_json=request,
            request_archive=request_archive,
        )


def test_extracted_content_must_match_verified_archive_bytes(tmp_path: Path) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    request, request_archive = _transport(fixture, artifact_root)
    submission = artifact_root / "SUBMISSION.json"
    submission.write_bytes(submission.read_bytes() + b" ")

    with pytest.raises(ProtectedBootstrapError, match="UNTRUSTED_ARTIFACT_CONTENT_MISMATCH"):
        verify_untrusted_artifact(
            artifact_root,
            event,
            _policy()[0],
            request_json=request,
            request_archive=request_archive,
        )


def test_bootstrap_receipts_cannot_be_upgraded_under_enabled_policy(tmp_path: Path) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    request, request_archive = _transport(fixture, artifact_root)
    verified = verify_untrusted_artifact(
        artifact_root,
        event,
        _policy()[0],
        request_json=request,
        request_archive=request_archive,
    )

    with pytest.raises(
        ProtectedBootstrapError,
        match="BOOTSTRAP_PACKAGE_FORBIDDEN_WHEN_POLICY_ENABLED",
    ):
        build_bootstrap_receipts(verified, policy_enabled=True)


def test_preexisting_candidate_package_is_not_used_as_trusted_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "input"
    _materialize_raw_artifact(artifact_root)
    package = artifact_root / PACKAGE_RELATIVE
    package.parent.mkdir(mode=0o700)
    package.write_bytes(b"candidate-controlled")
    event = _event(tmp_path)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    request, request_archive = _transport(fixture, artifact_root)

    with pytest.raises(ProducerPackageError, match="UNTRUSTED_ARTIFACT_LAYOUT_INVALID"):
        build_protected_bootstrap_package(
            artifact_root,
            event,
            request_json=request,
            request_archive=request_archive,
        )

    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "helper1_producer_package.py",
            "extract-subject",
            "--producer-package",
            str(package),
            "--output",
            str(tmp_path / "subject.json"),
        ],
    )
    assert producer_package_main() == 1
    assert "ERROR_CODE=UNTRUSTED_ARTIFACT_LAYOUT_INVALID" in capsys.readouterr().out
