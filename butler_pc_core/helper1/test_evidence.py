"""Allowlisted test execution and machine-derived Helper1 evidence records."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .canonical_json import canonicalize_butler_cj1

ROOT = Path(__file__).resolve().parents[2]
class TestEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TestLaneSpec:
    lane_id: str
    argv: tuple[str, ...]
    cwd_rel: str
    report_kind: Literal["junit", "vitest", "xcresult", "unavailable"]
    report_name: str
    timeout_seconds: int
    required_capabilities: frozenset[str]
    expected_collected: int | None


@dataclass(frozen=True, slots=True)
class CheckSpec:
    check_id: str
    argv: tuple[str, ...]
    cwd_rel: str
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class LaneResult:
    schema_version: str
    lane_id: str
    source_commit: str
    source_tree: str
    argv: tuple[str, ...]
    cwd_rel: str
    return_code: int | None
    runner_name: str
    runner_version: str
    environment_digest: str
    started_at_epoch_s: int
    finished_at_epoch_s: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_path: str | None
    stderr_path: str | None
    report_sha256: str | None
    collected: int
    passed: int
    failed: int
    errors: int
    skipped: int
    blocked: int
    status: Literal["PASSED", "FAILED", "BLOCKED"]
    error_code: str

    def __post_init__(self) -> None:
        if self.schema_version != "butler.helper1.test-run-record.v1":
            raise TestEvidenceError("TEST_LANE_SCHEMA_INVALID")
        values = (self.collected, self.passed, self.failed, self.errors, self.skipped, self.blocked)
        if any(type(item) is not int or item < 0 for item in values):
            raise TestEvidenceError("TEST_LANE_COUNT_INVALID")
        if self.status == "BLOCKED":
            if values != (0, 0, 0, 0, 0, 1):
                raise TestEvidenceError("BLOCKED_LANE_HAS_COUNTS")
        elif self.blocked != 0 or self.collected != self.passed + self.failed + self.errors + self.skipped:
            raise TestEvidenceError("TEST_LANE_COUNT_MISMATCH")
        if self.finished_at_epoch_s < self.started_at_epoch_s:
            raise TestEvidenceError("TEST_LANE_TIME_INVALID")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CheckResult:
    schema_version: str
    check_id: str
    source_commit: str
    source_tree: str
    argv: tuple[str, ...]
    cwd_rel: str
    return_code: int | None
    started_at_epoch_s: int
    finished_at_epoch_s: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_path: str | None
    stderr_path: str | None
    status: Literal["PASSED", "FAILED", "BLOCKED"]
    error_code: str

    def __post_init__(self) -> None:
        if self.schema_version != "butler.helper1.check-run-record.v1":
            raise TestEvidenceError("CHECK_SCHEMA_INVALID")
        if self.finished_at_epoch_s < self.started_at_epoch_s:
            raise TestEvidenceError("CHECK_TIME_INVALID")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


LANES: dict[str, TestLaneSpec] = {
    "python-helper1-v4-original": TestLaneSpec(
        lane_id="python-helper1-v4-original",
        argv=(
            "{python}", "-m", "pytest", "-q",
            "tests/helper1_v2",
            "--deselect=tests/helper1_v2/test_self_selected_trust_regression.py::test_legacy_four_complete_without_approval_closure_never_reaches_code_pass",
            "--deselect=tests/helper1_v2/test_self_selected_trust_regression.py::test_protected_verifier_rejects_replayed_complete_approval_set",
            "--deselect=tests/helper1_v2/test_self_selected_trust_regression.py::test_missing_replay_store_returns_unsigned_zero_verdict",
            "--deselect=tests/helper1_v2/test_self_selected_trust_regression.py::test_replay_store_connection_failure_returns_unsigned_zero_verdict",
            "--deselect=tests/helper1_v2/test_self_selected_trust_regression.py::test_replay_store_reservation_failure_returns_unsigned_zero_verdict",
            "--deselect=tests/helper1_v2/test_self_selected_trust_regression.py::test_external_evidence_mutation_after_package_creation_is_blocked",
            "--deselect=tests/helper1_v2/test_self_selected_trust_regression.py::test_valid_but_different_external_inventory_cannot_override_package",
            "--deselect=tests/helper1_v2/test_self_selected_trust_regression.py::test_approval_inventory_without_manifest_binding_is_blocked",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_protected_success_path_invokes_a4_closure_before_verdict",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_existing_helper1_codeowners_rules_are_preserved_and_a4_is_owned",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_handoff_chain_authority_is_fixed_outside_the_candidate_package",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_package_and_self_selected_authority_joint_mutation_is_rejected",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_producer_uploads_raw_material_and_protected_side_creates_fixed_package",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_producer_package_fingerprint_matches_candidate_descriptor",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_uploaded_artifact_roundtrip_preserves_exact_verifier_path",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_missing_renamed_or_substituted_package_blocks_final_gate",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_same_reservation_is_rejected_by_second_process",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_atomic_reservation_has_one_concurrent_winner",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_conninfo_rejects_routing_overrides_tls_downgrades_and_local_endpoints",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_rejects_driver_resolved_private_endpoint",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_rejects_any_private_dns_answer_before_connecting",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_pins_every_resolved_host_port_and_address",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_routing_environment_is_rejected_before_connecting",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_postgresql_probe_fails_closed_without_protected_dsn",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_clean_runner_executes_raw_to_package_to_unsigned_verdict",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_actual_github_response_shape_and_failed_sibling_job_are_accepted",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_unsuccessful_untrusted_job_blocks_before_packaging",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_workflow_byte_drift_blocks_before_packaging",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_policy_workflow_fingerprints_must_match_at_load",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_provenance_workflow_fingerprint_must_match_canonical_policy",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_current_workflow_fingerprint_reaches_unsigned_zero",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_workflow_fingerprint_is_not_duplicated_in_execution_code",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_downloaded_archive_digest_mismatch_blocks_before_packaging",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_extracted_content_must_match_verified_archive_bytes",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_bootstrap_receipts_cannot_be_upgraded_under_enabled_policy",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_preexisting_candidate_package_is_not_used_as_trusted_input",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_raw_only_producer_artifact_layout_is_accepted",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_raw_producer_artifact_missing_file_is_blocked",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_raw_producer_artifact_renamed_file_is_blocked",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_raw_producer_artifact_unknown_top_level_entry_is_blocked",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_protected_package_layout_still_requires_package",
            "--deselect=tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_artifact_redirect_does_not_forward_github_authorization",
            "--deselect=tests/helper1_v2/test_approval_input_v61.py",
            "--deselect=tests/helper1_v2/test_approval_transport_v61.py",
            "--deselect=tests/helper1_v2/test_device_measurement_v61.py",
            "--deselect=tests/helper1_v2/test_retrieval_quality_v61.py",
            "--deselect=tests/helper1_v2/test_start_tree_v61.py",
            "--deselect=tests/helper1_v2/test_protected_workflow_topology.py::test_transitive_dependency_omission_is_detected_automatically",
            "--junitxml={report}",
        ),
        cwd_rel=".",
        report_kind="junit",
        report_name="python-helper1-v4-original.junit.xml",
        timeout_seconds=300,
        required_capabilities=frozenset({"python", "pytest", "fastapi", "clang"}),
        expected_collected=243,
    ),
    "python-helper1-v51-targeted": TestLaneSpec(
        lane_id="python-helper1-v51-targeted",
        argv=(
            "{python}", "-m", "pytest", "-q",
            "tests/helper1_v2/test_a4_closure_v51.py",
            "tests/helper1_v2/test_canonical_json_v51.py",
            "tests/helper1_v2/test_deterministic_vectors_v51.py",
            "tests/helper1_v2/test_evidence_envelope_v51.py",
            "tests/helper1_v2/test_policy_authority_v51.py",
            "tests/helper1_v2/test_regressions_v51.py",
            "tests/helper1_v2/test_replay_store_v51.py",
            "tests/helper1_v2/test_test_evidence_v51.py",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_same_reservation_is_rejected_by_second_process",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_atomic_reservation_has_one_concurrent_winner",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_conninfo_rejects_routing_overrides_tls_downgrades_and_local_endpoints",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_rejects_driver_resolved_private_endpoint",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_rejects_any_private_dns_answer_before_connecting",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_pins_every_resolved_host_port_and_address",
            "--deselect=tests/helper1_v2/test_replay_store_v51.py::test_postgresql_routing_environment_is_rejected_before_connecting",
            "--junitxml={report}",
        ),
        cwd_rel=".",
        report_kind="junit",
        report_name="python-helper1-v51-targeted.junit.xml",
        timeout_seconds=180,
        required_capabilities=frozenset({"python", "pytest", "cryptography", "sqlite"}),
        expected_collected=149,
    ),
    "python-helper1-v61-quality": TestLaneSpec(
        lane_id="python-helper1-v61-quality",
        argv=(
            "{python}", "-m", "pytest", "-q",
            "tests/helper1_v2/test_approval_input_v61.py",
            "tests/helper1_v2/test_approval_transport_v61.py",
            "tests/helper1_v2/test_device_measurement_v61.py",
            "tests/helper1_v2/test_retrieval_quality_v61.py",
            "tests/helper1_v2/test_start_tree_v61.py",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_transitive_dependency_omission_is_detected_automatically",
            "--junitxml={report}",
        ),
        cwd_rel=".",
        report_kind="junit",
        report_name="python-helper1-v61-quality.junit.xml",
        timeout_seconds=180,
        required_capabilities=frozenset({"python", "pytest", "cryptography"}),
        expected_collected=32,
    ),
    "python-helper1-protected-replay": TestLaneSpec(
        lane_id="python-helper1-protected-replay",
        argv=(
            "{python}", "-m", "pytest", "-q",
            "tests/helper1_v2/test_self_selected_trust_regression.py::test_legacy_four_complete_without_approval_closure_never_reaches_code_pass",
            "tests/helper1_v2/test_self_selected_trust_regression.py::test_protected_verifier_rejects_replayed_complete_approval_set",
            "tests/helper1_v2/test_self_selected_trust_regression.py::test_missing_replay_store_returns_unsigned_zero_verdict",
            "tests/helper1_v2/test_self_selected_trust_regression.py::test_replay_store_connection_failure_returns_unsigned_zero_verdict",
            "tests/helper1_v2/test_self_selected_trust_regression.py::test_replay_store_reservation_failure_returns_unsigned_zero_verdict",
            "tests/helper1_v2/test_self_selected_trust_regression.py::test_external_evidence_mutation_after_package_creation_is_blocked",
            "tests/helper1_v2/test_self_selected_trust_regression.py::test_valid_but_different_external_inventory_cannot_override_package",
            "tests/helper1_v2/test_self_selected_trust_regression.py::test_approval_inventory_without_manifest_binding_is_blocked",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_protected_success_path_invokes_a4_closure_before_verdict",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_existing_helper1_codeowners_rules_are_preserved_and_a4_is_owned",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_handoff_chain_authority_is_fixed_outside_the_candidate_package",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_package_and_self_selected_authority_joint_mutation_is_rejected",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_producer_uploads_raw_material_and_protected_side_creates_fixed_package",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_producer_package_fingerprint_matches_candidate_descriptor",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_uploaded_artifact_roundtrip_preserves_exact_verifier_path",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_missing_renamed_or_substituted_package_blocks_final_gate",
            "tests/helper1_v2/test_replay_store_v51.py::test_same_reservation_is_rejected_by_second_process",
            "tests/helper1_v2/test_replay_store_v51.py::test_postgresql_atomic_reservation_has_one_concurrent_winner",
            "tests/helper1_v2/test_replay_store_v51.py::test_postgresql_conninfo_rejects_routing_overrides_tls_downgrades_and_local_endpoints",
            "tests/helper1_v2/test_replay_store_v51.py::test_postgresql_rejects_driver_resolved_private_endpoint",
            "tests/helper1_v2/test_replay_store_v51.py::test_postgresql_rejects_any_private_dns_answer_before_connecting",
            "tests/helper1_v2/test_replay_store_v51.py::test_postgresql_pins_every_resolved_host_port_and_address",
            "tests/helper1_v2/test_replay_store_v51.py::test_postgresql_routing_environment_is_rejected_before_connecting",
            "tests/helper1_v2/test_protected_workflow_topology.py::test_postgresql_probe_fails_closed_without_protected_dsn",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_clean_runner_executes_raw_to_package_to_unsigned_verdict",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_actual_github_response_shape_and_failed_sibling_job_are_accepted",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_unsuccessful_untrusted_job_blocks_before_packaging",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_workflow_byte_drift_blocks_before_packaging",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_policy_workflow_fingerprints_must_match_at_load",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_provenance_workflow_fingerprint_must_match_canonical_policy",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_current_workflow_fingerprint_reaches_unsigned_zero",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_workflow_fingerprint_is_not_duplicated_in_execution_code",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_downloaded_archive_digest_mismatch_blocks_before_packaging",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_extracted_content_must_match_verified_archive_bytes",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_bootstrap_receipts_cannot_be_upgraded_under_enabled_policy",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_preexisting_candidate_package_is_not_used_as_trusted_input",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_raw_only_producer_artifact_layout_is_accepted",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_raw_producer_artifact_missing_file_is_blocked",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_raw_producer_artifact_renamed_file_is_blocked",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_raw_producer_artifact_unknown_top_level_entry_is_blocked",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_protected_package_layout_still_requires_package",
            "tests/helper1_v2/test_protected_evidence_bootstrap_cycle.py::test_artifact_redirect_does_not_forward_github_authorization",
            "--junitxml={report}",
        ),
        cwd_rel=".",
        report_kind="junit",
        report_name="python-helper1-protected-replay.junit.xml",
        timeout_seconds=180,
        required_capabilities=frozenset({"python", "pytest", "cryptography", "sqlite"}),
        expected_collected=42,
    ),
    "desktop-helper1-v51": TestLaneSpec(
        lane_id="desktop-helper1-v51",
        argv=(
            "{npm}", "exec", "vitest", "run", "--", "--reporter=json",
            "--outputFile={report}",
        ),
        cwd_rel="butler-desktop",
        report_kind="vitest",
        report_name="desktop-helper1-v51.vitest.json",
        timeout_seconds=300,
        required_capabilities=frozenset({"node", "npm", "vitest"}),
        expected_collected=460,
    ),
    "native-macos-helper1-v51": TestLaneSpec(
        lane_id="native-macos-helper1-v51",
        argv=(),
        cwd_rel="butler-desktop/src-tauri",
        report_kind="unavailable",
        report_name="native-macos-helper1-v51.xcresult",
        timeout_seconds=1,
        required_capabilities=frozenset({"macos", "locked-xcode-scheme"}),
        expected_collected=None,
    ),
}

CHECKS: dict[str, CheckSpec] = {
    "python-helper1-collect-v51": CheckSpec(
        "python-helper1-collect-v51",
        ("{python}", "-m", "pytest", "--collect-only", "-q", "tests/helper1_v2"),
        ".",
        120,
    ),
    "desktop-lock-install-v51": CheckSpec(
        "desktop-lock-install-v51",
        ("{npm}", "ci", "--ignore-scripts"),
        "butler-desktop",
        300,
    ),
    "python-compileall-v51": CheckSpec(
        "python-compileall-v51",
        ("{python}", "-m", "compileall", "-q", "butler_pc_core", "scripts", "tests"),
        ".",
        120,
    ),
    "helper1-static-verifier-v51": CheckSpec(
        "helper1-static-verifier-v51",
        ("{python}", "scripts/verify_helper1_v2.py", "--static-only"),
        ".",
        120,
    ),
    "helper1-mutation-gate-v51": CheckSpec(
        "helper1-mutation-gate-v51",
        ("{python}", "scripts/helper1_mutation_gate.py"),
        ".",
        180,
    ),
    "desktop-typecheck-v51": CheckSpec(
        "desktop-typecheck-v51",
        ("{npm}", "exec", "tsc", "--", "--noEmit"),
        "butler-desktop",
        180,
    ),
    "git-diff-check-v51": CheckSpec(
        "git-diff-check-v51",
        ("{git}", "diff", "--check"),
        ".",
        60,
    ),
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_environment() -> dict[str, str]:
    allowed = ("PATH", "HOME", "TMPDIR", "SYSTEMROOT", "WINDIR")
    result = {name: os.environ[name] for name in allowed if name in os.environ}
    result.update({"PYTHONHASHSEED": "0", "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"})
    return result


def _git(argv: tuple[str, ...], *, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ("git", *argv), cwd=ROOT, env=env, shell=False, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
    )
    if completed.returncode != 0:
        raise TestEvidenceError("TEST_SOURCE_IDENTITY_UNAVAILABLE")
    return completed.stdout.decode("ascii").strip()


def _source_identity() -> tuple[str, str]:
    commit = _git(("rev-parse", "HEAD^{commit}"))
    with tempfile.TemporaryDirectory(prefix="helper1-v51-evidence-index-") as name:
        object_directory = Path(name) / "objects"
        object_directory.mkdir(mode=0o700)
        environment = dict(os.environ)
        environment["GIT_INDEX_FILE"] = str(Path(name) / "index")
        environment["GIT_OBJECT_DIRECTORY"] = str(object_directory)
        environment["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(ROOT / ".git" / "objects")
        _git(("read-tree", "HEAD"), env=environment)
        _git(("add", "-A"), env=environment)
        tree = _git(("write-tree",), env=environment)
    return commit, tree


def parse_junit_bytes(raw: bytes) -> tuple[int, int, int, int, int]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise TestEvidenceError("JUNIT_REPORT_INVALID") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise TestEvidenceError("JUNIT_REPORT_INVALID")
    tests = failures = errors = skipped = 0
    try:
        for suite in suites:
            tests += int(suite.attrib["tests"])
            failures += int(suite.attrib.get("failures", "0"))
            errors += int(suite.attrib.get("errors", "0"))
            skipped += int(suite.attrib.get("skipped", "0"))
    except (KeyError, ValueError) as exc:
        raise TestEvidenceError("JUNIT_REPORT_INVALID") from exc
    passed = tests - failures - errors - skipped
    if passed < 0:
        raise TestEvidenceError("JUNIT_REPORT_INVALID")
    return tests, passed, failures, errors, skipped


def parse_junit(path: Path) -> tuple[int, int, int, int, int]:
    try:
        return parse_junit_bytes(path.read_bytes())
    except OSError as exc:
        raise TestEvidenceError("JUNIT_REPORT_INVALID") from exc


def parse_vitest_bytes(raw: bytes) -> tuple[int, int, int, int, int]:
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TestEvidenceError("VITEST_REPORT_INVALID") from exc
    if type(value) is not dict:
        raise TestEvidenceError("VITEST_REPORT_INVALID")
    keys = ("numTotalTests", "numPassedTests", "numFailedTests", "numPendingTests")
    if any(type(value.get(key)) is not int or value[key] < 0 for key in keys):
        raise TestEvidenceError("VITEST_REPORT_INVALID")
    total, passed, failed, skipped = (value[key] for key in keys)
    if total != passed + failed + skipped:
        raise TestEvidenceError("VITEST_REPORT_INVALID")
    return total, passed, failed, 0, skipped


def parse_vitest(path: Path) -> tuple[int, int, int, int, int]:
    try:
        return parse_vitest_bytes(path.read_bytes())
    except OSError as exc:
        raise TestEvidenceError("VITEST_REPORT_INVALID") from exc


def _parse_report(spec: TestLaneSpec, path: Path) -> tuple[int, int, int, int, int]:
    if spec.report_kind == "junit":
        return parse_junit(path)
    if spec.report_kind == "vitest":
        return parse_vitest(path)
    raise TestEvidenceError("XCODE_RESULT_PARSER_UNAVAILABLE")


def _runner_version(spec: TestLaneSpec, environment: dict[str, str]) -> tuple[str, str]:
    if spec.lane_id.startswith("python"):
        argv = (sys.executable, "-m", "pytest", "--version")
        runner = "pytest"
        cwd = ROOT
    else:
        argv = ("npm", "exec", "vitest", "--", "--version")
        runner = "vitest"
        cwd = ROOT / spec.cwd_rel
    completed = subprocess.run(
        argv, cwd=cwd, env=environment, shell=False,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=10, check=False,
    )
    if completed.returncode != 0:
        return runner, "UNAVAILABLE"
    return runner, completed.stdout.decode("ascii", errors="ignore").strip()


def _blocked_record(spec: TestLaneSpec, code: str, started: int) -> LaneResult:
    commit, tree = _source_identity()
    return LaneResult(
        "butler.helper1.test-run-record.v1", spec.lane_id, commit, tree, spec.argv,
        spec.cwd_rel, None, spec.report_kind, "UNAVAILABLE",
        _digest(canonicalize_butler_cj1({"required_capabilities": sorted(spec.required_capabilities)})),
        started, int(time.time()), _digest(b""), _digest(b""), None, None, None,
        0, 0, 0, 0, 0, 1, "BLOCKED", code,
    )


def _write_raw_streams(output_root: Path, record_id: str, stdout: bytes, stderr: bytes) -> tuple[str, str]:
    raw_root = output_root / "raw"
    raw_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stdout_path = raw_root / f"{record_id}.stdout.log"
    stderr_path = raw_root / f"{record_id}.stderr.log"
    if any(path.exists() or path.is_symlink() for path in (stdout_path, stderr_path)):
        raise TestEvidenceError("RAW_TEST_OUTPUT_ALREADY_EXISTS")
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    return (
        stdout_path.relative_to(output_root).as_posix(),
        stderr_path.relative_to(output_root).as_posix(),
    )


def run_test_lane(lane_id: str, output_root: Path) -> LaneResult:
    """Execute one repository-owned lane. No argv, cwd or env is caller supplied."""
    spec = LANES.get(lane_id)
    if spec is None:
        raise TestEvidenceError("TEST_LANE_NOT_ALLOWLISTED")
    if not isinstance(output_root, Path):
        raise TestEvidenceError("TEST_OUTPUT_ROOT_INVALID")
    started = int(time.time())
    if spec.report_kind == "unavailable":
        return _blocked_record(spec, "MACOS_NATIVE_LANE_NOT_CONFIGURED", started)
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    report = output_root / spec.report_name
    if report.exists() or report.is_symlink():
        raise TestEvidenceError("TEST_REPORT_ALREADY_EXISTS")
    environment = _safe_environment()
    app_data = output_root / "app-data" / spec.lane_id
    app_data.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment["BUTLER_APP_DATA_DIR"] = str(app_data.resolve())
    argv = tuple(item.format(python=sys.executable, npm="npm", report=str(report)) for item in spec.argv)
    try:
        completed = subprocess.run(
            argv, cwd=ROOT / spec.cwd_rel, env=environment, shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=spec.timeout_seconds, check=False,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
        code = "TEST_LANE_TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "TEST_LANE_UNAVAILABLE"
        return _blocked_record(spec, code, started)
    stdout = completed.stdout
    stderr = completed.stderr
    stdout_path, stderr_path = _write_raw_streams(output_root, spec.lane_id, stdout, stderr)
    try:
        counts = _parse_report(spec, report)
        report_digest = _digest(report.read_bytes())
    except (TestEvidenceError, OSError):
        return _blocked_record(spec, "TEST_EVIDENCE_PARSE_FAILED", started)
    status: Literal["PASSED", "FAILED", "BLOCKED"] = (
        "PASSED"
        if completed.returncode == 0
        and counts[2] == 0
        and counts[3] == 0
        and (spec.expected_collected is None or counts[0] == spec.expected_collected)
        else "FAILED"
    )
    commit, tree = _source_identity()
    runner_name, runner_version = _runner_version(spec, environment)
    environment_digest = _digest(
        canonicalize_butler_cj1(
            {
                "names": sorted(environment),
                "path_sha256": _digest(environment.get("PATH", "").encode("utf-8")),
                "required_capabilities": sorted(spec.required_capabilities),
            }
        )
    )
    return LaneResult(
        "butler.helper1.test-run-record.v1", spec.lane_id, commit, tree, spec.argv,
        spec.cwd_rel, completed.returncode, runner_name, runner_version,
        environment_digest, started, int(time.time()), _digest(stdout), _digest(stderr),
        stdout_path, stderr_path, report_digest, *counts, 0, status,
        "NONE" if status == "PASSED" else "TEST_LANE_FAILED",
    )


def run_check(check_id: str, output_root: Path) -> CheckResult:
    """Run one fixed repository check and preserve its exact bounded-input output."""
    spec = CHECKS.get(check_id)
    if spec is None:
        raise TestEvidenceError("CHECK_NOT_ALLOWLISTED")
    started = int(time.time())
    environment = _safe_environment()
    app_data = output_root / "app-data" / spec.check_id
    app_data.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment["BUTLER_APP_DATA_DIR"] = str(app_data.resolve())
    argv = tuple(item.format(python=sys.executable, npm="npm", git="git") for item in spec.argv)
    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT / spec.cwd_rel,
            env=environment,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=spec.timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
        commit, tree = _source_identity()
        code = "CHECK_TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "CHECK_UNAVAILABLE"
        return CheckResult(
            "butler.helper1.check-run-record.v1", spec.check_id, commit, tree,
            spec.argv, spec.cwd_rel, None, started, int(time.time()), _digest(b""),
            _digest(b""), None, None, "BLOCKED", code,
        )
    commit, tree = _source_identity()
    status: Literal["PASSED", "FAILED", "BLOCKED"] = "PASSED" if completed.returncode == 0 else "FAILED"
    stdout_path, stderr_path = _write_raw_streams(
        output_root, spec.check_id, completed.stdout, completed.stderr
    )
    return CheckResult(
        "butler.helper1.check-run-record.v1", spec.check_id, commit, tree,
        spec.argv, spec.cwd_rel, completed.returncode, started, int(time.time()),
        _digest(completed.stdout), _digest(completed.stderr), stdout_path, stderr_path, status,
        "NONE" if status == "PASSED" else "CHECK_FAILED",
    )


def build_evidence_index(
    results: tuple[LaneResult, ...],
    checks: tuple[CheckResult, ...] = (),
) -> dict[str, object]:
    if not results or len({item.lane_id for item in results}) != len(results):
        raise TestEvidenceError("TEST_EVIDENCE_INVENTORY_INVALID")
    if len({item.check_id for item in checks}) != len(checks):
        raise TestEvidenceError("CHECK_EVIDENCE_INVENTORY_INVALID")
    source_trees = {item.source_tree for item in (*results, *checks)}
    if len(source_trees) != 1:
        raise TestEvidenceError("TEST_EVIDENCE_SOURCE_TREE_MISMATCH")
    return {
        "schema_version": "butler.helper1.test-evidence-index.v1",
        "source_tree": next(iter(source_trees)),
        "lanes": [item.to_dict() for item in sorted(results, key=lambda item: item.lane_id)],
        "checks": [item.to_dict() for item in sorted(checks, key=lambda item: item.check_id)],
        "required_lanes_blocked": sum(item.blocked for item in results),
        "all_required_lanes_passed": all(item.status == "PASSED" for item in results),
        "all_required_checks_passed": bool(checks) and all(item.status == "PASSED" for item in checks),
    }
