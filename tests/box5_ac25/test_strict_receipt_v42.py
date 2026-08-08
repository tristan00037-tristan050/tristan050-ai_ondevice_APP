from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from ac25 import delivery_manifest as dm
from ac25 import strict_receipt as sr
from ac25 import strict_receipt_validator as validator

pytestmark = pytest.mark.no_sidecar_token


@pytest.fixture(autouse=True)
def local_command_transport(monkeypatch):
    """Exercise semantics on macOS without weakening the Linux production path."""
    def run(argv: list[str], *, cwd: Path, env=None):
        completed = subprocess.run(
            argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False,
        )
        return completed.returncode, completed.stdout
    monkeypatch.setattr(validator, "_run_command", run)


def command(cwd: Path, *argv: str, binary: bool = False):
    completed = subprocess.run(
        list(argv), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout if binary else completed.stdout.decode("ascii").strip()


def put(path: Path, document) -> bytes:
    raw = sr.canonical_json_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def refresh(delivery: Path, receipt: dict | None = None) -> None:
    root = delivery / validator.RECEIPT_DIRNAME
    if receipt is not None:
        put(root / "receipt.json", receipt)
    (root / "DIGESTS.sha256").write_bytes(sr.build_digest_manifest(root))
    (delivery / "DIGESTS.sha256").unlink(missing_ok=True)
    (delivery / "DIGESTS.sha256").write_bytes(dm.build_delivery_digests(delivery))


def build_test_manifest(root: Path, kind: str, filename: str, raw: bytes, parser) -> bytes:
    (root / kind).mkdir(parents=True, exist_ok=True)
    (root / kind / filename).write_bytes(raw)
    counts = parser(raw).as_dict()
    return put(root / kind / "manifest.json", {
        "files": [{
            "bytes": len(raw), "counts": counts, "path": f"{kind}/{filename}",
            "sha256": sr.sha256_bytes(raw),
        }],
        "summary": counts,
    })


def make_delivery(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    command(repo, "git", "init", "-q")
    command(repo, "git", "config", "user.name", "AC25 Test")
    command(repo, "git", "config", "user.email", "ac25@example.invalid")
    workflow = repo / validator.WORKFLOW_PATH
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: Box5 AC-25 Stage A Smoke\n", encoding="utf-8")
    command(repo, "git", "add", ".")
    command(repo, "git", "commit", "-q", "-m", "start")
    start = command(repo, "git", "rev-parse", "HEAD")
    start_tree = command(repo, "git", "show", "-s", "--format=%T", start)
    erratum = repo / validator.ERRATUM_PATH
    erratum.parent.mkdir(parents=True)
    erratum.write_text(
        '{"canonical_output_policy":"OUTSIDE_REPOSITORY_ONLY","cleanup_to_achieve_clean":"FORBIDDEN","dirty_path_allowlist":"FORBIDDEN","policy_id":"AC25_R6_ERRATUM_2","raw_final_worktree_clean":"REQUIRED","schema_version":"butler.ac25.scope-policy.v1","unknown_state":"FAIL_CLOSED"}\n',
        encoding="utf-8",
    )
    (repo / "allowed.txt").write_text("target\n", encoding="utf-8")
    command(repo, "git", "add", ".")
    command(repo, "git", "commit", "-q", "-m", "target")
    command(repo, "git", "branch", "-M", "feat/box5-ac25-trusted-verification")
    target = command(repo, "git", "rev-parse", "HEAD")
    target_tree = command(repo, "git", "show", "-s", "--format=%T", target)
    workflow_blob = command(repo, "git", "rev-parse", f"{target}:{validator.WORKFLOW_PATH}")

    delivery = tmp_path / "AC25_R6_CLOSE_v42_DELIVERY"
    root = delivery / validator.RECEIPT_DIRNAME
    root.mkdir(parents=True)
    schema_source = Path(__file__).resolve().parents[2] / "docs/box5/ac25/receipt.schema.json"
    (root / "receipt.schema.json").write_bytes(schema_source.read_bytes())

    expected = ["A_OK", "B_OK"]
    inventory_raw = sr.canonical_json_bytes({"guards": expected, "target_head_sha": target})
    contract_stdout = (
        b"A" + b"_OK=" + b"1\n" + b"B" + b"_OK=" + b"1\n"
        + b"REPO_CONTRACTS_FAILED_GUARD=NONE\n"
    )
    (root / "contract").mkdir()
    (root / "contract/contract.stdout").write_bytes(contract_stdout)
    contract = {
        "command_plan_sha256": "1" * 64,
        "expected_inventory": expected,
        "expected_inventory_sha256": sr.sha256_bytes(inventory_raw),
        "failing_guard_keys": [],
        "observed_guards": {"A_OK": "1", "B_OK": "1"},
        "parse_error_code": "NONE", "primary_failed_guard": "NONE",
        "process_exit_code": 0, "target_head_sha": target,
        "raw_stdout_bytes": len(contract_stdout),
        "raw_stdout_path": "contract/contract.stdout",
        "raw_stdout_sha256": sr.sha256_bytes(contract_stdout),
    }
    contract_raw = put(root / "contract_evidence.json", contract)
    clean_raw_file = b""
    (root / "clean-status.porcelain-v2.z").write_bytes(clean_raw_file)
    clean = {
        "clean_check_executed": True, "dirty_path_count": 0,
        "erratum_2_sha256": validator.ERRATUM_SHA256,
        "git_status_exit_code": 0, "output_root_location": "OUTSIDE_REPOSITORY_ONLY",
        "outside_proposed_set_count": 0, "post_run_cleanup_used": False,
        "raw_final_worktree_clean": True,
        "raw_status_path": "clean-status.porcelain-v2.z",
        "raw_status_sha256": sr.sha256_bytes(clean_raw_file),
        "target_head_sha": target,
    }
    clean_raw = put(root / "clean_check.json", clean)
    changed_nul = command(
        repo, "git", "diff", "--name-only", "-z", "--no-renames", start, target,
        binary=True,
    )
    (delivery / "changed_paths.nul").write_bytes(changed_nul)
    paths = [part.decode("utf-8") for part in changed_nul.split(b"\0") if part]
    changed_raw = put(root / "changed_paths.json", {"base": start, "head": target, "paths": paths})
    (delivery / "changed_paths.json").write_bytes(changed_raw)
    required = {
        "branch_protection_pages_complete": True,
        "checks": [{"app_id": 123, "name": "required-ci"}],
        "complete": True, "known": True, "ruleset_pages_complete": True,
        "source": "branch-protection",
    }
    required_raw = put(root / "required_checks.json", required)
    observed = {
        "checks": [{
            "app_id": 123, "attempt": 1, "conclusion": "success",
            "name": "required-ci", "run_id": 8, "status": "completed",
        }],
        "complete": True, "head_sha": target,
    }
    observed_raw = put(root / "observed_checks.json", observed)
    junit_raw = b'<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite>'
    tap_raw = b"TAP version 13\n1..1\nok 1 - success\n"
    junit_manifest_raw = build_test_manifest(root, "junit", "results.xml", junit_raw, sr.parse_junit)
    tap_manifest_raw = build_test_manifest(root, "tap", "results.tap", tap_raw, sr.parse_tap)
    provenance = {
        "commands": [
            {"argv": list(argv), "exit_code": 0} for argv in validator.REQUIRED_COMMANDS
        ],
        "clean_check_command_index": len(validator.REQUIRED_COMMANDS) - 1,
        "exact_head_job_id": "9", "job_attempt": "1",
        "job_conclusion": "success", "job_head_sha": target,
        "job_name": validator.EXACT_HEAD_JOB_NAME, "job_run_id": "7",
        "job_status": "completed", "pr_number": 904,
        "receipt_issued_at": "2026-08-07T03:02:00Z",
        "repository": validator.REPOSITORY, "run_attempt": "1",
        "run_completed_at": "2026-08-07T03:01:00Z",
        "run_conclusion": "success", "run_event": "pull_request",
        "run_id": "7", "run_started_at": "2026-08-07T03:00:00Z",
        "run_status": "completed", "start_head_sha": start,
        "target_head_sha": target, "target_head_tree": target_tree,
        "workflow_blob_oid": workflow_blob, "workflow_id": validator.WORKFLOW_ID,
        "workflow_path": validator.WORKFLOW_PATH,
    }
    provenance_raw = put(root / "provenance.json", provenance)
    receipt = {
        "changed_path_manifest_sha256": sr.sha256_bytes(changed_raw),
        "clean_check_sha256": sr.sha256_bytes(clean_raw),
        "command_plan_sha256": "1" * 64,
        "contract_evidence_sha256": sr.sha256_bytes(contract_raw),
        "erratum_2_sha256": validator.ERRATUM_SHA256,
        "exact_head_job_id": "9",
        "expected_guard_inventory_sha256": contract["expected_inventory_sha256"],
        "junit_manifest_sha256": sr.sha256_bytes(junit_manifest_raw),
        "observed_checks_sha256": sr.sha256_bytes(observed_raw),
        "pr_base_sha_observed": "7" * 40, "pr_number": 904,
        "provenance_sha256": sr.sha256_bytes(provenance_raw),
        "receipt_issued_at": provenance["receipt_issued_at"],
        "repository": validator.REPOSITORY,
        "required_checks_sha256": sr.sha256_bytes(required_raw),
        "run_attempt": "1", "run_completed_at": provenance["run_completed_at"],
        "run_id": "7", "run_started_at": provenance["run_started_at"],
        "schema_version": sr.SCHEMA_VERSION, "start_head_sha": start,
        "start_head_tree": start_tree,
        "tap_manifest_sha256": sr.sha256_bytes(tap_manifest_raw),
        "target_head_sha": target, "target_head_tree": target_tree,
        "workflow_blob_oid": workflow_blob, "workflow_id": validator.WORKFLOW_ID,
        "workflow_path": validator.WORKFLOW_PATH,
    }
    put(root / "receipt.json", receipt)
    (delivery / "START_HEAD").write_text(start + "\n", encoding="ascii")
    (delivery / "TARGET_HEAD").write_text(target + "\n", encoding="ascii")
    (delivery / "TARGET_TREE").write_text(target_tree + "\n", encoding="ascii")
    (delivery / "README.md").write_text("AC25 R6 Close v4.2\n", encoding="utf-8")
    (delivery / "cumulative.patch").write_bytes(
        command(repo, "git", "diff", "--binary", "--full-index", start, target, binary=True)
    )
    command(
        repo, "git", "bundle", "create", str(delivery / "candidate.bundle"),
        validator.CANDIDATE_REF, f"^{start}",
    )
    refresh(delivery)
    return delivery, repo, receipt, contract, clean, required, observed, provenance


def mutate_json(delivery: Path, receipt: dict, filename: str, digest_key: str, document: dict):
    root = delivery / validator.RECEIPT_DIRNAME
    raw = put(root / filename, document)
    receipt[digest_key] = sr.sha256_bytes(raw)
    refresh(delivery, receipt)


def mutate_contract_raw(delivery: Path, receipt: dict, contract: dict, raw: bytes) -> None:
    root = delivery / validator.RECEIPT_DIRNAME
    (root / "contract/contract.stdout").write_bytes(raw)
    parsed = validator.contract_parse.parse_contract_output(raw)
    contract.update({
        "failing_guard_keys": list(parsed.failing_guard_keys),
        "observed_guards": {
            key: value for key, value in parsed.keys if key.endswith("_OK")
        },
        "parse_error_code": parsed.parse_error_code,
        "primary_failed_guard": parsed.primary_failed_guard,
        "raw_stdout_bytes": len(raw),
        "raw_stdout_sha256": sr.sha256_bytes(raw),
    })
    mutate_json(
        delivery, receipt, "contract_evidence.json", "contract_evidence_sha256",
        contract,
    )


def fake_remote(receipt, *, run_conclusion="success", job_conclusion="success", check_conclusion="success"):
    def fetch(url: str):
        if "/pulls/" in url:
            return {"head": {"sha": receipt["target_head_sha"]}}
        if "/git/commits/" in url:
            return {"tree": {"sha": receipt["target_head_tree"]}}
        if "/actions/runs/" in url:
            return {
                "conclusion": run_conclusion, "event": "pull_request",
                "head_sha": receipt["target_head_sha"], "id": int(receipt["run_id"]),
                "path": validator.WORKFLOW_PATH,
                "run_attempt": int(receipt["run_attempt"]), "status": "completed",
                "workflow_id": validator.WORKFLOW_ID,
            }
        if "/actions/jobs/" in url:
            return {
                "conclusion": job_conclusion, "head_sha": receipt["target_head_sha"],
                "id": int(receipt["exact_head_job_id"]),
                "name": validator.EXACT_HEAD_JOB_NAME,
                "run_attempt": int(receipt["run_attempt"]),
                "run_id": int(receipt["run_id"]), "status": "completed",
            }
        if "/protection/required_status_checks" in url:
            return {"checks": [{"app_id": 123, "context": "required-ci"}], "contexts": []}
        if "/rulesets?" in url:
            return []
        if "/check-runs?" in url:
            return {"check_runs": [{
                "app": {"id": 123}, "conclusion": check_conclusion, "id": 8,
                "name": "required-ci", "status": "completed",
            }]}
        raise AssertionError(url)
    return fetch


def assert_blocked(result, code):
    assert result.ac25_pass is False
    assert result.error_code == code
    assert validator._process_exit("gate", result) != 0


def test_valid_delivery_is_diagnostic_valid_but_offline_gate_stays_closed(tmp_path):
    delivery, repo, *_ = make_delivery(tmp_path)
    result = validator.validate_delivery(delivery, repo)
    assert result.receipt_valid and result.evidence_valid
    assert result.remote_binding == "NOT_RUN"
    assert_blocked(result, "REMOTE_BINDING_NOT_RUN")


def test_valid_delivery_passes_only_with_live_success_binding(tmp_path):
    delivery, repo, receipt, *_ = make_delivery(tmp_path)
    result = validator.validate_delivery(delivery, repo, online=True, fetch=fake_remote(receipt))
    assert result == validator.ValidationResult(True, True, "PASS", True, "OK")


def test_t01_35_failed_guards_never_pass(tmp_path):
    delivery, repo, receipt, contract, *_ = make_delivery(tmp_path)
    keys = [f"AUDIT_{index:02d}_OK" for index in range(35)]
    contract.update({
        "expected_inventory": keys,
        "expected_inventory_sha256": sr.sha256_bytes(sr.canonical_json_bytes({"guards": keys, "target_head_sha": receipt["target_head_sha"]})),
    })
    receipt["expected_guard_inventory_sha256"] = contract["expected_inventory_sha256"]
    mutate_contract_raw(
        delivery, receipt, contract,
        ("".join(f"{key}=0\n" for key in keys) + "REPO_CONTRACTS_FAILED_GUARD=NONE\n").encode(),
    )
    assert_blocked(validator.validate_delivery(delivery, repo), "CONTRACT_GUARDS_FAILED")


def test_t02_empty_contract_inventory_never_passes(tmp_path):
    delivery, repo, receipt, contract, *_ = make_delivery(tmp_path)
    contract.update({
        "expected_inventory": [],
        "expected_inventory_sha256": sr.sha256_bytes(sr.canonical_json_bytes({"guards": [], "target_head_sha": receipt["target_head_sha"]})),
    })
    receipt["expected_guard_inventory_sha256"] = contract["expected_inventory_sha256"]
    mutate_contract_raw(
        delivery, receipt, contract, b"REPO_CONTRACTS_FAILED_GUARD=NONE\n",
    )
    assert_blocked(validator.validate_delivery(delivery, repo), "CONTRACT_INVENTORY_EMPTY")


@pytest.mark.parametrize("field,value", [("gates", {"mb01": True}), ("ac25_pass", True), ("receipt_outcome", "PASS")])
def test_t03_t04_self_asserted_results_are_rejected(tmp_path, field, value):
    delivery, repo, receipt, *_ = make_delivery(tmp_path)
    receipt[field] = value
    refresh(delivery, receipt)
    assert_blocked(validator.validate_delivery(delivery, repo), "SELF_ASSERTED_GATE_MISMATCH")


def test_t05_empty_required_and_observed_sets_never_pass(tmp_path):
    delivery, repo, receipt, _contract, _clean, required, observed, _ = make_delivery(tmp_path)
    required["checks"] = []
    observed["checks"] = []
    mutate_json(delivery, receipt, "required_checks.json", "required_checks_sha256", required)
    mutate_json(delivery, receipt, "observed_checks.json", "observed_checks_sha256", observed)
    assert_blocked(validator.validate_delivery(delivery, repo), "REQUIRED_CHECK_SET_EMPTY")


def test_t06_missing_required_identity_never_passes(tmp_path):
    delivery, repo, receipt, _contract, _clean, _required, observed, _ = make_delivery(tmp_path)
    observed["checks"] = []
    mutate_json(delivery, receipt, "observed_checks.json", "observed_checks_sha256", observed)
    assert_blocked(validator.validate_delivery(delivery, repo), "REQUIRED_CHECK_MISSING")


def test_t07_required_app_id_mismatch_never_passes(tmp_path):
    delivery, repo, receipt, _contract, _clean, _required, observed, _ = make_delivery(tmp_path)
    observed["checks"][0]["app_id"] = 999
    mutate_json(delivery, receipt, "observed_checks.json", "observed_checks_sha256", observed)
    assert_blocked(validator.validate_delivery(delivery, repo), "REQUIRED_CHECK_APP_ID_MISMATCH")


def test_t08_failed_remote_run_never_passes(tmp_path):
    delivery, repo, receipt, *_ = make_delivery(tmp_path)
    assert_blocked(
        validator.validate_delivery(delivery, repo, online=True, fetch=fake_remote(receipt, run_conclusion="failure")),
        "REMOTE_RUN_NOT_SUCCESS",
    )


def test_t09_failed_remote_job_never_passes(tmp_path):
    delivery, repo, receipt, *_ = make_delivery(tmp_path)
    assert_blocked(
        validator.validate_delivery(delivery, repo, online=True, fetch=fake_remote(receipt, job_conclusion="failure")),
        "REMOTE_JOB_NOT_SUCCESS",
    )


@pytest.mark.parametrize("conclusion", ["cancelled", "skipped", "timed_out"])
def test_t10_non_success_remote_state_never_passes(tmp_path, conclusion):
    delivery, repo, receipt, *_ = make_delivery(tmp_path)
    assert_blocked(
        validator.validate_delivery(delivery, repo, online=True, fetch=fake_remote(receipt, run_conclusion=conclusion)),
        "REMOTE_RUN_NOT_SUCCESS",
    )


def test_required_check_non_success_never_passes(tmp_path):
    delivery, repo, receipt, *_ = make_delivery(tmp_path)
    assert_blocked(
        validator.validate_delivery(delivery, repo, online=True, fetch=fake_remote(receipt, check_conclusion="cancelled")),
        "REQUIRED_CHECK_NOT_SUCCESS",
    )


def test_t11_failed_required_command_never_passes(tmp_path):
    delivery, repo, receipt, _contract, _clean, _required, _observed, provenance = make_delivery(tmp_path)
    provenance["commands"][1]["exit_code"] = 1
    mutate_json(delivery, receipt, "provenance.json", "provenance_sha256", provenance)
    assert_blocked(validator.validate_delivery(delivery, repo), "PROVENANCE_COMMAND_FAILED")


def test_t11_cleanup_command_never_passes(tmp_path):
    delivery, repo, receipt, _contract, _clean, _required, _observed, provenance = make_delivery(tmp_path)
    provenance["commands"].insert(
        -1, {"argv": ["git", "reset", "--hard", "HEAD"], "exit_code": 0},
    )
    provenance["clean_check_command_index"] += 1
    mutate_json(delivery, receipt, "provenance.json", "provenance_sha256", provenance)
    assert_blocked(validator.validate_delivery(delivery, repo), "POST_RUN_CLEANUP_FORBIDDEN")


def test_t11_clean_check_must_be_final_command(tmp_path):
    delivery, repo, receipt, _contract, _clean, _required, _observed, provenance = make_delivery(tmp_path)
    provenance["commands"].append({"argv": ["true"], "exit_code": 0})
    mutate_json(delivery, receipt, "provenance.json", "provenance_sha256", provenance)
    assert_blocked(
        validator.validate_delivery(delivery, repo),
        "PROVENANCE_CLEAN_CHECK_ORDER_INVALID",
    )


def test_t12_junit_failure_never_passes(tmp_path):
    delivery, repo, receipt, *_ = make_delivery(tmp_path)
    root = delivery / validator.RECEIPT_DIRNAME
    raw = b'<testsuite tests="1" failures="1" errors="0" skipped="0"><testcase><failure/></testcase></testsuite>'
    manifest = build_test_manifest(root, "junit", "results.xml", raw, sr.parse_junit)
    receipt["junit_manifest_sha256"] = sr.sha256_bytes(manifest)
    refresh(delivery, receipt)
    assert_blocked(validator.validate_delivery(delivery, repo), "JUNIT_NOT_SUCCESS")


def test_t13_schema_forbidden_field_is_rejected(tmp_path):
    delivery, repo, receipt, *_ = make_delivery(tmp_path)
    receipt["surprise"] = 1
    refresh(delivery, receipt)
    assert_blocked(validator.validate_delivery(delivery, repo), "RECEIPT_SCHEMA_INVALID")


def test_t14_patch_and_bundle_tree_mismatch_is_rejected(tmp_path):
    delivery, repo, receipt, *_ = make_delivery(tmp_path)
    (repo / "allowed.txt").write_text("alternate\n", encoding="utf-8")
    command(repo, "git", "add", "allowed.txt")
    command(repo, "git", "commit", "-q", "-m", "alternate")
    alternate = command(repo, "git", "rev-parse", "HEAD")
    (delivery / "cumulative.patch").write_bytes(
        command(repo, "git", "diff", "--binary", "--full-index", receipt["start_head_sha"], alternate, binary=True)
    )
    refresh(delivery)
    assert_blocked(validator.validate_delivery(delivery, repo), "DELIVERY_REPRODUCTION_MISMATCH")


def test_t15_erratum_digest_mismatch_is_rejected(tmp_path):
    delivery, repo, receipt, _contract, clean, *_ = make_delivery(tmp_path)
    clean["erratum_2_sha256"] = "0" * 64
    mutate_json(delivery, receipt, "clean_check.json", "clean_check_sha256", clean)
    assert_blocked(validator.validate_delivery(delivery, repo), "ERRATUM_2_DIGEST_MISMATCH")


def test_cli_separates_diagnose_from_gate_and_is_meta_only(tmp_path, capsys):
    delivery, repo, *_ = make_delivery(tmp_path)
    diagnose = validator.main(["diagnose", "--delivery-root", str(delivery), "--repository", str(repo)])
    lines = capsys.readouterr().out.splitlines()
    assert diagnose == 0
    assert lines == [
        "RECEIPT_VALID=1", "EVIDENCE_VALID=1", "REMOTE_BINDING=NOT_RUN",
        "AC25_PASS=0", "ERROR_CODE=REMOTE_BINDING_NOT_RUN",
    ]
    gate = validator.main(["gate", "--delivery-root", str(delivery), "--repository", str(repo)])
    assert gate == 1
    assert len(capsys.readouterr().out.splitlines()) == 5


def test_committed_erratum_has_exact_bytes_and_digest():
    path = Path(__file__).resolve().parents[2] / validator.ERRATUM_PATH
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert hashlib.sha256(raw).hexdigest() == validator.ERRATUM_SHA256
