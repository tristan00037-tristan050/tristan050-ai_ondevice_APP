from __future__ import annotations

import copy
import json
import subprocess
import unicodedata
from pathlib import Path

import pytest
from ac25 import delivery_manifest as dm
from ac25 import strict_receipt as sr
from ac25 import strict_receipt_validator as validator

pytestmark = pytest.mark.no_sidecar_token


@pytest.fixture(autouse=True)
def local_git_transport(monkeypatch):
    """macOS lacks the protected Linux subreaper; inject only the test transport."""
    def query(repository: Path, argv: list[str], *, binary: bool = False):
        completed = subprocess.run(
            ["git", *argv], cwd=repository, check=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed.stdout if binary else completed.stdout.decode("ascii").strip()
    monkeypatch.setattr(validator, "_run_git", query)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    return result.stdout.strip()


def put_json(path: Path, value) -> bytes:
    raw = sr.canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def make_repository(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "AC25 Test")
    git(repo, "config", "user.email", "ac25@example.invalid")
    workflow = repo / ".github/workflows/box5-ac25-stage-a-smoke.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: test\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "start")
    start = git(repo, "rev-parse", "HEAD")
    start_tree = git(repo, "show", "-s", "--format=%T", "HEAD")
    (repo / "allowed.txt").write_text("target\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "target")
    target = git(repo, "rev-parse", "HEAD")
    target_tree = git(repo, "show", "-s", "--format=%T", "HEAD")
    workflow_blob = git(repo, "rev-parse", f"{target}:.github/workflows/box5-ac25-stage-a-smoke.yml")
    return repo, start, start_tree, target, target_tree, workflow_blob


def make_bundle(tmp_path: Path):
    repo, start, start_tree, target, target_tree, workflow_blob = make_repository(tmp_path)
    root = tmp_path / "AC25_R6_CLOSE_RECEIPT"
    (root / "junit").mkdir(parents=True)
    (root / "tap").mkdir()

    junit_raw = (
        b'<testsuite tests="2" failures="1" errors="0" skipped="0">'
        b'<testcase name="a"/><testcase name="b"><failure/></testcase></testsuite>'
    )
    tap_raw = b"TAP version 13\n1..2\nok 1 - a\nnot ok 2 - b # TODO fix\n"
    (root / "junit/results.xml").write_bytes(junit_raw)
    (root / "tap/results.tap").write_bytes(tap_raw)
    junit_manifest = {
        "files": [{
            "bytes": len(junit_raw), "counts": sr.parse_junit(junit_raw).as_dict(),
            "path": "junit/results.xml", "sha256": sr.sha256_bytes(junit_raw),
        }],
        "summary": sr.parse_junit(junit_raw).as_dict(),
    }
    tap_manifest = {
        "files": [{
            "bytes": len(tap_raw), "counts": sr.parse_tap(tap_raw).as_dict(),
            "path": "tap/results.tap", "sha256": sr.sha256_bytes(tap_raw),
        }],
        "summary": sr.parse_tap(tap_raw).as_dict(),
    }
    junit_manifest_raw = put_json(root / "junit/manifest.json", junit_manifest)
    tap_manifest_raw = put_json(root / "tap/manifest.json", tap_manifest)

    changed = {"base": start, "head": target, "paths": ["allowed.txt"]}
    changed_raw = put_json(root / "changed_paths.json", changed)
    dirty_raw = put_json(root / "dirty_paths.json", {
        "declared_policy": "WAITING_ERRATUM_2", "paths": [],
        "raw_final_worktree_clean": "YES",
    })
    guards_raw = put_json(root / "failing_guard_keys.json", {"keys": []})
    required_raw = put_json(root / "required_checks.json", {
        "checks": [], "complete": False, "known": False, "source": "UNKNOWN",
    })
    observed_raw = put_json(root / "observed_checks.json", {
        "checks": [], "complete": False, "head_sha": target,
    })
    provenance = {
        "approval_issued_at": None,
        "commands": [
            {"argv": ["python3", "-S", "-c", "import ac25.repo_contract_runner, ac25.strict_receipt_validator"], "exit_code": 0},
            {"argv": ["python3", "-m", "pytest", "-q", "tests/box5_ac25"], "exit_code": 0},
            {"argv": ["node", "--test", "tests/box5_ac25/publish_check.test.mjs"], "exit_code": 0},
        ],
        "exact_head_job_id": "3", "pr_number": 904,
        "receipt_issued_at": "2026-08-07T01:02:00Z",
        "repository": "tristan00037-tristan050/tristan050-ai_ondevice_APP",
        "run_attempt": "1", "run_completed_at": "2026-08-07T01:01:00Z",
        "run_id": "2", "run_started_at": "2026-08-07T01:00:00Z",
        "start_head_sha": start, "target_head_sha": target,
        "target_head_tree": target_tree, "workflow_blob_oid": workflow_blob,
        "workflow_path": ".github/workflows/box5-ac25-stage-a-smoke.yml",
    }
    provenance_raw = put_json(root / "provenance.json", provenance)
    schema = Path(__file__).resolve().parents[2] / "docs/box5/ac25/receipt.schema.json"
    (root / "receipt.schema.json").write_bytes(schema.read_bytes())
    receipt = {
        "ac25_pass": False,
        "changed_path_manifest_sha256": sr.sha256_bytes(changed_raw),
        "command_plan_sha256": "1" * 64,
        "dirty_path_manifest_sha256": sr.sha256_bytes(dirty_raw),
        "exact_head_job_id": "3", "failing_guard_keys_sha256": sr.sha256_bytes(guards_raw),
        "gates": {"mb01": True, "mb02": False, "mb03": False, "mb04": True, "mb05": True, "remote_binding": False},
        "guard_manifest_sha256": sr.sha256_bytes(guards_raw),
        "junit_manifest_sha256": sr.sha256_bytes(junit_manifest_raw),
        "observed_checks_sha256": sr.sha256_bytes(observed_raw),
        "pr_base_sha_observed": "7" * 40, "pr_number": 904,
        "provenance_sha256": sr.sha256_bytes(provenance_raw),
        "receipt_issued_at": provenance["receipt_issued_at"], "receipt_outcome": "FAIL",
        "repository": provenance["repository"], "required_checks_sha256": "UNKNOWN",
        "run_attempt": "1", "run_completed_at": provenance["run_completed_at"],
        "run_id": "2", "run_started_at": provenance["run_started_at"],
        "schema_version": sr.SCHEMA_VERSION, "start_head_sha": start,
        "start_head_tree": start_tree, "tap_manifest_sha256": sr.sha256_bytes(tap_manifest_raw),
        "target_head_sha": target, "target_head_tree": target_tree,
        "workflow_blob_oid": workflow_blob,
    }
    put_json(root / "receipt.json", receipt)
    refresh_digests(root)
    return root, repo, receipt, provenance


def refresh_digests(root: Path):
    (root / "DIGESTS.sha256").write_bytes(sr.build_digest_manifest(root))


def rewrite_receipt(root: Path, receipt: dict):
    put_json(root / "receipt.json", receipt)
    refresh_digests(root)


def test_valid_failure_receipt_is_accepted_but_ac25_stays_false(tmp_path):
    root, repo, _receipt, _provenance = make_bundle(tmp_path)
    result = validator.validate_bundle(root, repo)
    assert result.valid and result.error_code == "OK" and result.ac25_pass is False


def test_receipt_cannot_claim_ac25_pass_when_any_gate_fails(tmp_path):
    root, repo, receipt, _ = make_bundle(tmp_path)
    receipt["ac25_pass"] = True
    receipt["receipt_outcome"] = "PASS"
    rewrite_receipt(root, receipt)
    assert validator.validate_bundle(root, repo).error_code == "AC25_PASS_CONTRADICTORY"


def test_missing_raw_junit_rejected(tmp_path):
    root, repo, _receipt, _ = make_bundle(tmp_path)
    (root / "junit/results.xml").unlink()
    refresh_digests(root)
    assert validator.validate_bundle(root, repo).error_code == "JUNIT_RAW_NOT_FOUND"


def test_junit_declared_count_mismatch_rejected(tmp_path):
    raw = b'<testsuite tests="2" failures="0" errors="0" skipped="0"><testcase/></testsuite>'
    with pytest.raises(sr.StrictReceiptError, match="JUNIT_COUNT_MISMATCH"):
        sr.parse_junit(raw)


def test_junit_doctype_and_entity_rejected():
    with pytest.raises(sr.StrictReceiptError, match="JUNIT_DTD_FORBIDDEN"):
        sr.parse_junit(b'<!DOCTYPE x [<!ENTITY y "z">]><testsuite/>')


def test_nested_junit_not_double_counted():
    raw = (
        b'<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
        b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
        b'<testcase/></testsuite></testsuite></testsuites>'
    )
    assert sr.parse_junit(raw).tests == 1


def test_missing_tap_plan_rejected():
    with pytest.raises(sr.StrictReceiptError, match="TAP_PLAN_MISSING"):
        sr.parse_tap(b"ok 1 - x\n")


def test_tap_duplicate_number_rejected():
    with pytest.raises(sr.StrictReceiptError, match="TAP_DUPLICATE_NUMBER"):
        sr.parse_tap(b"1..2\nok 1 - x\nok 1 - y\n")


def test_tap_yaml_diagnostics_are_metadata_not_test_points():
    raw = b"TAP version 13\nok 1 - x\n  ---\n  duration_ms: 1\n  ...\n1..1\n"
    assert sr.parse_tap(raw).as_dict() == {
        "not_ok": 0, "ok": 1, "skipped": 0, "tests": 1, "todo": 0,
    }


def test_changed_path_manifest_bytes_required():
    with pytest.raises(sr.StrictReceiptError, match="CHANGED_PATH_NUL_TERMINATOR_MISSING"):
        dm.changed_paths_from_nul(b"allowed.txt")


def test_changed_path_set_must_match_git_diff_exactly(tmp_path):
    root, repo, receipt, _ = make_bundle(tmp_path)
    raw = put_json(root / "changed_paths.json", {"base": receipt["start_head_sha"], "head": receipt["target_head_sha"], "paths": []})
    receipt["changed_path_manifest_sha256"] = sr.sha256_bytes(raw)
    rewrite_receipt(root, receipt)
    assert validator.validate_bundle(root, repo).error_code == "CHANGED_PATH_SET_MISMATCH"


def test_unknown_field_rejected(tmp_path):
    root, repo, receipt, _ = make_bundle(tmp_path)
    receipt["unknown"] = True
    rewrite_receipt(root, receipt)
    assert validator.validate_bundle(root, repo).error_code == "JSON_UNKNOWN_FIELD"


def test_duplicate_json_key_rejected():
    with pytest.raises(sr.StrictReceiptError, match="JSON_DUPLICATE_KEY"):
        sr.loads_strict(b'{"x":1,"x":1}\n')


def test_head_tree_mismatch_rejected(tmp_path):
    root, repo, receipt, _ = make_bundle(tmp_path)
    receipt["target_head_tree"] = "a" * 40
    rewrite_receipt(root, receipt)
    assert validator.validate_bundle(root, repo).error_code == "PROVENANCE_BINDING_MISMATCH"


def remote_fetch(receipt, *, attempt=None):
    def fetch(url):
        if "/pulls/" in url:
            return {"head": {"sha": receipt["target_head_sha"]}}
        if "/git/commits/" in url:
            return {"tree": {"sha": receipt["target_head_tree"]}}
        if "/actions/runs/" in url:
            return {"id": int(receipt["run_id"]), "head_sha": receipt["target_head_sha"], "run_attempt": int(attempt or receipt["run_attempt"])}
        return {"id": int(receipt["exact_head_job_id"]), "run_id": int(receipt["run_id"]), "run_attempt": int(receipt["run_attempt"]), "head_sha": receipt["target_head_sha"]}
    return fetch


def test_run_attempt_mismatch_rejected(tmp_path):
    root, repo, receipt, _ = make_bundle(tmp_path)
    result = validator.validate_bundle(root, repo, online=True, fetch=remote_fetch(receipt, attempt=2))
    assert result.error_code == "RUN_ATTEMPT_MISMATCH"


def test_workflow_blob_mismatch_rejected(tmp_path):
    root, repo, receipt, provenance = make_bundle(tmp_path)
    receipt["workflow_blob_oid"] = "a" * 40
    provenance["workflow_blob_oid"] = "a" * 40
    provenance_raw = put_json(root / "provenance.json", provenance)
    receipt["provenance_sha256"] = sr.sha256_bytes(provenance_raw)
    rewrite_receipt(root, receipt)
    assert validator.validate_bundle(root, repo).error_code == "WORKFLOW_BLOB_MISMATCH"


def test_receipt_issued_before_run_completion_rejected(tmp_path):
    root, repo, receipt, _ = make_bundle(tmp_path)
    receipt["receipt_issued_at"] = "2026-08-07T00:59:00Z"
    rewrite_receipt(root, receipt)
    assert validator.validate_bundle(root, repo).error_code == "RECEIPT_ISSUED_BEFORE_RUN_COMPLETION"


def test_approval_issued_after_run_rejected(tmp_path):
    root, repo, receipt, provenance = make_bundle(tmp_path)
    provenance["approval_issued_at"] = "2026-08-07T01:00:01Z"
    raw = put_json(root / "provenance.json", provenance)
    receipt["provenance_sha256"] = sr.sha256_bytes(raw)
    rewrite_receipt(root, receipt)
    assert validator.validate_bundle(root, repo).error_code == "APPROVAL_ISSUED_AFTER_RUN"


def test_required_set_unknown_cannot_pass_mb03(tmp_path):
    root, repo, receipt, _ = make_bundle(tmp_path)
    receipt["gates"]["mb03"] = True
    rewrite_receipt(root, receipt)
    assert validator.validate_bundle(root, repo).error_code == "MB03_GATE_CONTRADICTORY"


def test_digest_manifest_covers_every_file_except_itself(tmp_path):
    root, repo, _receipt, _ = make_bundle(tmp_path)
    (root / "extra.bin").write_bytes(b"x")
    assert validator.validate_bundle(root, repo).error_code == "DIGEST_MANIFEST_INCOMPLETE"


def test_path_traversal_and_unicode_collision_rejected():
    with pytest.raises(sr.StrictReceiptError):
        sr.validate_unique_paths(["../x"])
    nfc = "caf\u00e9.txt"
    nfd = unicodedata.normalize("NFD", nfc)
    with pytest.raises(sr.StrictReceiptError):
        sr.validate_unique_paths([nfc, nfd])
