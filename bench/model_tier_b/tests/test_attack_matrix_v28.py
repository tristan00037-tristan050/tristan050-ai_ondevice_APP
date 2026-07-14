from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from butler_bench.artifact_scanner import scan_artifact_tree
from butler_bench.attestation import (
    TrustPolicy, load_trust_policy, reject_outer_zip_self_signature,
    verify_in_toto_statement, verify_keyless_claims,
)
from butler_bench.canonical import canonical_sha256, sha256_bytes, sha256_file, write_canonical_json
from butler_bench.dual_resident import validate_dual_resident
from butler_bench.egress import validate_egress_receipt
from butler_bench.energy import reject_estimated_energy
from butler_bench.errors import ExitCode, FailClass, GateError
from butler_bench.evidence import EvidenceWriter, _verify_dag, build_artifact_manifest, verify_evidence_directory, verify_receipt
from butler_bench.governance import build_final_status
from butler_bench.independence import assert_offline_verifier_independent
from butler_bench.live_verifier import LiveSemanticVerifier
from butler_bench.memory import MEMORY_MARKS, validate_environment_receipt, validate_memory_receipt
from butler_bench.model_manifest import ModelIdentityGuard, build_model_manifest
from butler_bench.policy import load_approved_policy
from butler_bench.preflight import GATE_NAMES, validate_m3_gate_receipts, validate_m3_start_gates
from butler_bench.product_bridge import validate_product_module
from butler_bench.provenance import validate_full_oid, validate_provenance_receipt
from butler_bench.schedule import build_schedule, validate_cooldown, validate_epoch_set, verify_metrics_rows, verify_schedule
from butler_bench.terminal_gate import Stage, TerminalDecisionMachine, verify_terminal_evidence
from butler_bench.worker_protocol import EVENT_ORDER, PAYLOAD_KEYS, verify_worker_stream

from entrypoint_owner_attack_kit import run_entrypoint_owner_attack as _entrypoint_owner_attack

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "spec" / "v2.8" / "02_구현계약" / "attack_matrix_v2.8.csv"
SHA = "a" * 64
SHA_B = "b" * 64


def load_matrix() -> dict[str, dict[str, str]]:
    with MATRIX.open(encoding="utf-8-sig", newline="") as stream:
        return {row["attack_id"]: row for row in csv.DictReader(stream)}


MATRIX_ROWS = load_matrix()


def run_case(case_id: str) -> tuple[int, str]:
    row = MATRIX_ROWS[case_id]
    try:
        with tempfile.TemporaryDirectory(prefix=f"butler-{case_id.lower()}-") as directory:
            _dispatch(row["name"], Path(directory))
    except GateError as exc:
        broad = _broad_class(exc.fail_class)
        return int(exc.exit_code), broad
    return 0, "PASS"


def _broad_class(value: FailClass) -> str:
    direct = {
        FailClass.EVIDENCE, FailClass.SECURITY_PRIVACY, FailClass.EGRESS,
        FailClass.DUAL_RESIDENT, FailClass.PROTOCOL, FailClass.IDENTITY,
        FailClass.PROVENANCE, FailClass.POLICY_TRUST, FailClass.ATTESTATION,
        FailClass.PRODUCT_GATE, FailClass.INDEPENDENT_VERIFY, FailClass.PREFLIGHT,
        FailClass.SCHEDULE, FailClass.ENVIRONMENT_MEMORY, FailClass.MEASUREMENT,
    }
    if value in direct:
        return value.value
    mapping = {
        "EVIDENCE": {FailClass.ORPHAN_EVIDENCE, FailClass.DUPLICATE_EVIDENCE, FailClass.SCHEMA_INVALID, FailClass.DIGEST_MISMATCH},
        "IDENTITY": {FailClass.MODEL_PATH_UNSAFE, FailClass.MODEL_SWAP, FailClass.MODEL_MANIFEST_MISMATCH, FailClass.MODEL_IDENTITY_MISSING},
        "PRODUCT_GATE": {FailClass.FORBIDDEN_REPAIR, FailClass.FINAL_GATE_STALE, FailClass.FINAL_BEFORE_DLP, FailClass.TERMINAL_STATUS_MISMATCH},
    }
    for broad, values in mapping.items():
        if value in values:
            return broad
    return value.value


def _dispatch(name: str, root: Path) -> None:
    groups: tuple[tuple[set[str], Callable[[str, Path], None]], ...] = (
        ({"manifest_only_no_receipts", "receipt_orphan", "receipt_cycle", "duplicate_receipt_digest", "unknown_schema_field"}, _evidence_attack),
        ({"secret_payload_bin", "nul_secret_file", "archive_zip_bomb", "archive_path_traversal", "utf16_secret", "secret_in_exception_trace", "casefold_filename_collision"}, _scanner_attack),
        ({"forged_mock_egress", "nonexistent_pid_egress", "ipv6_only_escape", "dns_subprocess_escape", "controller_interval_gap"}, _egress_attack),
        ({"forged_dual_receipt", "same_model_both_candidates", "no_inference_overlap"}, _dual_attack),
        ({"synthetic_worker_events", "worker_replays_nonce", "parent_first_byte_forged", "stdout_flood", "partial_jsonl_tail", "descendant_process_leak"}, _worker_attack),
        ({"model_swap_after_hash", "model_symlink", "external_hardlink", "tokenizer_omitted", "lfs_pointer_as_model"}, _model_attack),
        ({"short_commit_oid", "dirty_worktree", "submodule_commit_mismatch", "git_blob_vs_sha_confusion"}, _provenance_attack),
        ({"duplicate_yaml_key", "policy_unset_default", "wildcard_signing_identity", "wrong_oidc_issuer", "attestation_wrong_subject"}, _policy_trust_attack),
        ({"outer_zip_self_signature_claim", "unsigned_ci_artifact_swap"}, _attestation_attack),
        ({"fake_product_module", "repair_on_dlp_failure", "repair_twice", "stale_primary_final", "terminal_before_dlp"}, _product_attack),
        ({"caller_supplied_validator", "producer_import_in_verifier"}, _independence_attack),
        ({"all_true_preflight_json", "p0_only_m3_start"}, _preflight_attack),
        ({"warmup_in_metrics", "abba_schedule_violation", "cooldown_config_not_elapsed", "invalid_epoch_cherry_pick"}, _schedule_attack),
        ({"sampler_gap_hidden", "rss_wrong_pid_scope", "thermal_critical_accepted", "metal_receipt_forged"}, _memory_attack),
        ({"energy_estimated_without_meter"}, _energy_attack),
        ({"entrypoint_owner_tamper_after_commit", "entrypoint_owner_untracked_file", "entrypoint_rebound_at_runtime"}, _entrypoint_owner_attack),
    )
    for names, handler in groups:
        if name in names:
            handler(name, root)
            return
    raise AssertionError(f"unhandled attack: {name}")


def _evidence_attack(name: str, root: Path) -> None:
    mandatory = [
        "source_provenance", "environment", "benchmark_policy", "model_identity_A",
        "model_identity_B", "runtime_config_A", "runtime_config_B", "fixture_manifest",
        "schedule", "worker_event_stream_index", "cold_worker", "live_semantic_verify",
        "epoch", "dual_resident", "os_egress", "ci", "raw_scan", "final_verdict",
    ]
    profile = {"profile_version": "v2.8", "mandatory_receipts": mandatory, "final_pointer": f"receipts/{SHA}.json", "max_receipts": 100}
    if name == "manifest_only_no_receipts":
        verify_evidence_directory(root, profile)
    if name == "receipt_orphan":
        _verify_dag({"a": {"parents": []}, "b": {"parents": []}}, "a")
    if name == "receipt_cycle":
        _verify_dag({"a": {"parents": [{"receipt_sha256": "a"}]}}, "a")
    if name == "duplicate_receipt_digest":
        writer = EvidenceWriter(root, "run")
        kwargs = {"receipt_type": "ci", "subject": [{"name": "ci", "sha256": SHA}], "parents": [], "payload": {}, "created_at_utc": "2026-07-14T00:00:00Z"}
        writer.write_receipt(**kwargs)
        writer.write_receipt(**kwargs)
    if name == "unknown_schema_field":
        writer = EvidenceWriter(root, "run")
        path, _ = writer.write_receipt("ci", subject=[{"name": "ci", "sha256": SHA}], parents=[], payload={})
        value = json.loads(path.read_text())
        value["unknown"] = True
        verify_receipt(value)


def _scanner_attack(name: str, root: Path) -> None:
    policy = _scanner_policy()
    if name == "secret_payload_bin":
        data = b"\x00password=supersecretvalue"
        (root / "payload.bin").write_bytes(data)
        policy["registered_binary_profiles"].append(_binary_profile("payload.bin", data, "00", False))
    elif name == "nul_secret_file":
        (root / "payload.dat").write_bytes(b"\x00secret=supersecretvalue")
    elif name in {"archive_zip_bomb", "archive_path_traversal"}:
        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if name == "archive_zip_bomb": archive.writestr("large.txt", b"0" * 1_000_000)
            else: archive.writestr("../escape.txt", b"safe")
        data = output.getvalue()
        (root / "evidence.zip").write_bytes(data)
        policy["registered_binary_profiles"].append(_binary_profile("evidence.zip", data, "504b0304", True))
    elif name == "utf16_secret":
        data = "password=supersecretvalue".encode("utf-16le")
        (root / "utf16.bin").write_bytes(data)
        policy["registered_binary_profiles"].append(_binary_profile("utf16.bin", data, data[:2].hex(), False))
    elif name == "secret_in_exception_trace":
        (root / "trace.log").write_text("RuntimeError: token=supersecretvalue\n", encoding="utf-8")
    elif name == "casefold_filename_collision":
        (root / "Report.txt").write_text("one", encoding="utf-8")
        (root / "report.TXT").write_text("two", encoding="utf-8")
    manifest = build_artifact_manifest(root)
    scan_artifact_tree(root, manifest, policy)


def _egress_attack(name: str, root: Path) -> None:
    policy = {"allowed_outbound_attempts": 0, "approved_controller_profiles": {"NETWORK_EXTENSION_CONTENT_FILTER": {"binary_sha256": SHA, "policy_sha256": SHA_B}}}
    receipt = {
        "schema_version": "butler.model-tier-b.os-egress.v2.8", "controller_type": "NETWORK_EXTENSION_CONTENT_FILTER",
        "controller_binary_sha256": SHA, "policy_sha256": SHA_B, "activation_monotonic_ns": 50,
        "deactivation_monotonic_ns": 300, "target_pid_set": [101, 102], "child_process_scope_verified": True,
        "failure_default": "DENY", "denied_attempt_count": 5, "allowed_attempt_count": 0,
        "native_ipv4_probe": "DENIED", "native_ipv6_probe": "DENIED", "dns_probe": "DENIED",
        "https_probe": "DENIED", "subprocess_probe": "DENIED",
    }
    if name == "forged_mock_egress": receipt["controller_type"] = "mock"
    elif name == "nonexistent_pid_egress": receipt["target_pid_set"] = [999999]
    elif name == "ipv6_only_escape": receipt["native_ipv6_probe"] = "ALLOWED"
    elif name == "dns_subprocess_escape": receipt["subprocess_probe"] = "ALLOWED"
    elif name == "controller_interval_gap": receipt["activation_monotonic_ns"] = 150
    receipt["receipt_subject_sha256"] = canonical_sha256(receipt)
    validate_egress_receipt(receipt, policy=policy, expected_pid_set=[101, 102], run_start_ns=100, run_end_ns=200)


def _dual_attack(name: str, root: Path) -> None:
    policy = {"min_co_residency_seconds": 1, "max_swap_delta_bytes": 0}
    receipt = {
        "schema_version": "butler.model-tier-b.dual-resident.v2.8",
        "candidate_A": {"variant_id": "model-A", "model_manifest_sha256": SHA, "runtime_config_sha256": "c" * 64},
        "candidate_B": {"variant_id": "model-B", "model_manifest_sha256": SHA_B, "runtime_config_sha256": "d" * 64},
        "worker_pid_A": 101, "worker_pid_B": 102, "parent_observed_pid_set": [101, 102],
        "worker_executable_sha256_A": "e" * 64, "worker_executable_sha256_B": "f" * 64,
        "loaded_start_ns_A": 1_000_000_000, "loaded_end_ns_A": 4_000_000_000,
        "loaded_start_ns_B": 2_000_000_000, "loaded_end_ns_B": 5_000_000_000,
        "inference_intervals_A": [{"start_ns": 2_100_000_000, "end_ns": 2_300_000_000, "fixture_id": "fx", "stream_sha256": "1" * 64}],
        "inference_intervals_B": [{"start_ns": 2_400_000_000, "end_ns": 2_600_000_000, "fixture_id": "fx", "stream_sha256": "2" * 64}],
        "model_pre_sha256_A": SHA, "model_post_sha256_A": SHA,
        "model_pre_sha256_B": SHA_B, "model_post_sha256_B": SHA_B,
        "observer_stream_sha256": "3" * 64, "policy_bypass_count": 0, "oom_count": 0,
        "sampler_error_count": 0, "swap_delta_bytes": 0,
    }
    if name == "forged_dual_receipt": receipt["parent_observed_pid_set"] = [999998, 999999]
    elif name == "same_model_both_candidates": receipt["candidate_B"]["model_manifest_sha256"] = SHA
    elif name == "no_inference_overlap": receipt["inference_intervals_B"][0].update(start_ns=4_100_000_000, end_ns=4_200_000_000)
    validate_dual_resident(receipt, policy)


def _worker_attack(name: str, root: Path) -> None:
    stdout, expected, arrivals = _worker_fixture()
    stderr = b""
    if name == "synthetic_worker_events":
        events = _decode_events(stdout); events[0]["safe_payload"]["provenance_sha256"] = "9" * 64; _rehash(events[0]); stdout = _encode_events(events)
    elif name == "worker_replays_nonce":
        events = _decode_events(stdout)
        for event in events: event["challenge_sha256"] = "8" * 64
        stdout = _encode_events(events)
    elif name == "parent_first_byte_forged": arrivals[0] = 50
    elif name == "stdout_flood": stdout = stdout + b"x" * (4 * 1024 * 1024)
    elif name == "partial_jsonl_tail": stdout = stdout.rstrip(b"\n")
    elif name == "descendant_process_leak":
        events = _decode_events(stdout); events[-1]["safe_payload"]["descendant_count"] = 1; _rehash(events[-1]); stdout = _encode_events(events)
    verify_worker_stream(stdout, stderr, 0, expected=expected, parent_event_arrival_ns=arrivals, parent_pipe_write_complete_ns=150, parent_eof_ns=1000)


def _model_attack(name: str, root: Path) -> None:
    (root / "config.json").write_text("{}", encoding="utf-8")
    (root / "tokenizer.json").write_text("{}", encoding="utf-8")
    weights = root / "weights.bin"
    weights.write_bytes(b"weights")
    if name == "model_symlink":
        (root / "linked.bin").symlink_to(weights)
        build_model_manifest(root, metadata_sha256=SHA, variant_id="model-A")
    if name == "external_hardlink":
        os.link(weights, root / "hard.bin")
        build_model_manifest(root, metadata_sha256=SHA, variant_id="model-A")
    if name == "tokenizer_omitted":
        (root / "tokenizer.json").rename(root / "words.dat")
        build_model_manifest(root, metadata_sha256=SHA, variant_id="model-A")
    if name == "lfs_pointer_as_model":
        weights.write_text(f"version https://git-lfs.github.com/spec/v1\noid sha256:{SHA}\nsize 7\n", encoding="ascii")
        build_model_manifest(root, metadata_sha256=SHA, variant_id="model-A")
    manifest = build_model_manifest(root, metadata_sha256=SHA, variant_id="model-A")
    guard = ModelIdentityGuard(root, manifest); guard.verify_pre_generation(); weights.write_bytes(b"swapped"); guard.verify_post_generation()


def _provenance_attack(name: str, root: Path) -> None:
    receipt = _provenance_receipt()
    if name == "short_commit_oid": receipt["base_commit_oid"] = "d19badcd"
    elif name == "dirty_worktree": receipt["clean_tree"] = False
    elif name == "submodule_commit_mismatch": receipt["submodules"] = [{"path": "sub", "url": "https://example.invalid/sub", "commit_oid": "1" * 40, "tree_oid": "2" * 40, "status": "MISMATCH"}]
    elif name == "git_blob_vs_sha_confusion":
        validate_full_oid(SHA, "sha1")
        return
    validate_provenance_receipt(receipt)


def _policy_trust_attack(name: str, root: Path) -> None:
    if name in {"duplicate_yaml_key", "policy_unset_default"}:
        policy = _approved_policy()
        path = root / "policy.json"
        if name == "duplicate_yaml_key":
            text = json.dumps(policy, separators=(",", ":")); path.write_text(text[:-1] + ',"approval_status":"APPROVED"}', encoding="utf-8")
            load_approved_policy(path, expected_sha256=SHA)
        else:
            policy["approval_status"] = "UNSET"; write_canonical_json(path, policy)
            load_approved_policy(path, expected_sha256=canonical_sha256(policy), now=datetime(2026, 7, 14, tzinfo=timezone.utc))
        return
    trust = _trust_policy()
    if name == "wildcard_signing_identity":
        trust["certificate_identity"] = "*"
        path = root / "trust.json"; write_canonical_json(path, trust)
        load_trust_policy(path, expected_sha256=canonical_sha256(trust), now=datetime(2026, 7, 14, tzinfo=timezone.utc))
    policy = TrustPolicy(trust, canonical_sha256(trust))
    if name == "wrong_oidc_issuer":
        claims = _keyless_claims(trust); claims["issuer"] = "https://wrong.invalid"; verify_keyless_claims(claims, policy)
    if name == "attestation_wrong_subject":
        claims = _keyless_claims(trust); claims["subject_sha256"] = "0" * 64; verify_keyless_claims(claims, policy)


def _attestation_attack(name: str, root: Path) -> None:
    if name == "outer_zip_self_signature_claim": reject_outer_zip_self_signature("handoff.zip")
    trust = _trust_policy(); payload = root / "release.tar.gz"; payload.write_bytes(b"swapped")
    trust["subject_sha256"] = SHA
    path = root / "statement.json"; write_canonical_json(path, _statement(trust, SHA))
    verify_in_toto_statement(path, payload, TrustPolicy(trust, canonical_sha256(trust)))


def _product_attack(name: str, root: Path) -> None:
    if name == "fake_product_module":
        validate_product_module("fake_product", approved_product_root=root, expected_module_sha256=SHA, expected_commit_oid="1" * 40)
    machine = TerminalDecisionMachine()
    if name == "repair_twice": machine.record_repair(); machine.record_repair()
    if name == "terminal_before_dlp": machine.pass_final()
    machine.advance(Stage.IDENTITY_VALIDATED); machine.advance(Stage.GENERATION_DONE); machine.advance(Stage.PROVISIONAL_QUALITY_DECIDED)
    if name == "repair_on_dlp_failure":
        machine.record_repair(); machine.record_grounding(True); machine.record_dlp(False); machine.record_approval(True); machine.block("DLP_BLOCK")
    machine.record_grounding(True); machine.record_dlp(True); machine.record_approval(True); verdict = machine.pass_final().as_dict()
    if name == "stale_primary_final":
        events = [dict(item) for item in machine.safe_events]; events[1]["outcome"] = "SKIPPED"; verify_terminal_evidence(events, verdict)


def _independence_attack(name: str, root: Path) -> None:
    if name == "caller_supplied_validator": LiveSemanticVerifier(lambda _: True)
    path = root / "verify.py"; path.write_text("from butler_bench import canonical\n", encoding="utf-8")
    assert_offline_verifier_independent(path)


def _preflight_attack(name: str, root: Path) -> None:
    if name == "all_true_preflight_json": validate_m3_start_gates({"gates": {name: True for name in GATE_NAMES}})
    expected = {gate: SHA for gate in GATE_NAMES}
    validate_m3_gate_receipts([], expected_subjects=expected)


def _schedule_attack(name: str, root: Path) -> None:
    policy, fixtures = _schedule_inputs(); schedule = build_schedule(policy, fixtures)
    if name == "warmup_in_metrics": verify_metrics_rows([schedule["rows"][0]], schedule)
    if name == "abba_schedule_violation":
        measured = next(row for row in schedule["rows"] if row["phase"] == "measured" and row["repetition"] == 2)
        measured["candidate_id"] = "A" if measured["candidate_id"] == "B" else "B"
        unsigned = {key: value for key, value in schedule.items() if key != "schedule_sha256"}; schedule["schedule_sha256"] = canonical_sha256(unsigned)
        verify_schedule(schedule, policy, fixtures)
    if name == "cooldown_config_not_elapsed": validate_cooldown(1_000_000_000, 2_000_000_000)
    validate_epoch_set([{"epoch": 1, "valid": True, "aborted_run_count": 0}])


def _memory_attack(name: str, root: Path) -> None:
    policy = {"peak_rss_limit_bytes": 10_000, "available_memory_floor_bytes": 100, "sampler_interval_ms": 10, "max_missed_sample_ratio_ppm": 0, "require_metal": True}
    marks = []
    for index, mark in enumerate(MEMORY_MARKS, 1):
        marks.append({
            "mark": mark, "monotonic_ns": index, "target_pid_set": [101], "rss_bytes_total": 1000,
            "available_memory_bytes": 5000, "memory_pressure": "normal", "sample_source": "approved_sampler",
            "sample_interval_ms": 10, "missed_sample_count": 0, "sample_count": 10, "max_observed_gap_ms": 10,
            "metal_current_allocated_size_bytes": 0 if index == 1 else 100,
            "metal_recommended_max_working_set_size_bytes": 5000, "metal_unsupported_reason": None,
        })
    receipt = {"schema_version": "butler.model-tier-b.memory.v2.8", "sampler_binary_sha256": SHA, "sampler_config_sha256": SHA_B, "sampler_process_pid": 99, "raw_samples_sha256": "c" * 64, "marks": marks, "sampler_error_count": 0}
    if name == "sampler_gap_hidden": marks[3]["max_observed_gap_ms"] = 100
    elif name == "rss_wrong_pid_scope": marks[3]["target_pid_set"] = [999]
    elif name == "metal_receipt_forged": marks[2]["metal_current_allocated_size_bytes"] = -1
    elif name == "thermal_critical_accepted":
        environment = _environment_receipt(); environment["thermal_post"] = "critical"
        validate_environment_receipt(environment, target={"minimum_physical_memory_bytes": 1})
        return
    validate_memory_receipt(receipt, policy=policy, expected_pid_set=[101], approved_sampler_binary_sha256=SHA, approved_sampler_config_sha256=SHA_B)


def _energy_attack(name: str, root: Path) -> None:
    reject_estimated_energy(15, 2)


def _scanner_policy() -> dict[str, Any]:
    return {"schema_version": "butler.model-tier-b.scanner-policy.v2.8", "unregistered_file_action": "BLOCK", "unregistered_binary_action": "BLOCK", "encodings": ["ASCII", "UTF-8", "UTF-16LE", "UTF-16BE"], "max_depth": 4, "max_entries": 100, "max_total_expanded_bytes": 2_000_000, "max_single_file_bytes": 1_500_000, "max_compression_ratio": 100, "registered_binary_profiles": [], "forbidden_path_kinds": ["absolute", "parent_traversal", "symlink", "special", "casefold_collision"]}


def _binary_profile(path: str, data: bytes, magic: str, archive: bool) -> dict[str, Any]:
    return {"relative_path": path, "magic_hex": magic, "mime": "application/octet-stream" if not archive else "application/zip", "sha256": hashlib.sha256(data).hexdigest(), "max_bytes": len(data), "archive": archive}


def _worker_fixture() -> tuple[bytes, dict[str, Any], list[int]]:
    expected = {"challenge_sha256": "1" * 64, "worker_pid": 101, "parent_pid": 100, "executable_sha256": "2" * 64, "provenance_sha256": "3" * 64, "model_manifest_sha256": "4" * 64, "runtime_config_sha256": "5" * 64, "request_sha256": "6" * 64, "output_token_count": 3}
    payloads = [
        {"worker_pid": 101, "parent_pid": 100, "executable_sha256": "2" * 64, "provenance_sha256": "3" * 64},
        {"model_manifest_sha256": "4" * 64, "runtime_config_sha256": "5" * 64, "loader_fd_set_sha256": "7" * 64},
        {"fixture_id": "fx", "request_sha256": "6" * 64},
        {"token_count": 1, "output_prefix_sha256": "8" * 64},
        {"output_token_count": 3, "output_stream_sha256": "9" * 64},
        {"status": "PASS", "final_gate": "ALLOW", "fail_class": None, "verdict_sha256": "a" * 64},
        {"descendant_count": 0},
    ]
    events = []
    for index, (event_type, payload) in enumerate(zip(EVENT_ORDER, payloads, strict=True)):
        events.append({"schema_version": "butler.model-tier-b.worker-event.v2.8", "run_id": "run", "worker_id": "worker-A", "seq": index, "event_type": event_type, "monotonic_ns": 100 + index * 10, "wall_time_utc": "2026-07-14T00:00:00Z", "challenge_sha256": "1" * 64, "payload_sha256": canonical_sha256(payload), "safe_payload": payload})
    return _encode_events(events), expected, [200 + index * 10 for index in range(7)]


def _decode_events(data: bytes) -> list[dict[str, Any]]: return [json.loads(line) for line in data.splitlines()]
def _encode_events(events: list[dict[str, Any]]) -> bytes: return b"".join(json.dumps(event, sort_keys=True, separators=(",", ":")).encode() + b"\n" for event in events)
def _rehash(event: dict[str, Any]) -> None: event["payload_sha256"] = canonical_sha256(event["safe_payload"])


def _provenance_receipt() -> dict[str, Any]:
    return {"schema_version": "butler.model-tier-b.source-provenance.v2.8", "object_format": "sha1", "base_commit_oid": "1" * 40, "base_tree_oid": "2" * 40, "effective_commit_oid": "3" * 40, "effective_tree_oid": "4" * 40, "clean_tree": True, "submodules": [], "lfs_objects": [], "git_blob_manifest_sha256": SHA, "deployment_file_manifest_sha256": SHA_B}


def _approved_policy() -> dict[str, Any]:
    return {"schema_version": "butler.model-tier-b.benchmark-policy.v2.8", "approval_status": "APPROVED", "approver_identity": "owner@example.com", "approval_expiry_utc": "2030-01-01T00:00:00Z", "fixture_manifest_sha256": SHA, "candidates": {"A": {"variant_id": "model-A", "model_manifest_sha256": "1" * 64, "runtime_config_sha256": "2" * 64}, "B": {"variant_id": "model-B", "model_manifest_sha256": "3" * 64, "runtime_config_sha256": "4" * 64}}, "quality_floor_by_task": {"task": "0.8"}, "quality_noninferiority_margin_by_task": {"task": "0.05"}, "ttft_slo_ms_by_task": {"task": 1000}, "p95_e2e_slo_ms_by_task": {"task": 5000}, "peak_rss_limit_bytes": 1000000, "available_memory_floor_bytes": 100000, "max_repair_rate": "0.1", "max_cascade_rate": "0.01", "worker_deadline_seconds": 60, "min_co_residency_seconds": 15, "sampler_interval_ms": 10, "max_missed_sample_ratio": "0.01", "tokenizer_manifest_sha256": SHA_B, "bootstrap_seed": 1234, "bootstrap_iterations": 1000, "energy_required": False}


def _trust_policy() -> dict[str, Any]:
    return {"schema_version": "butler.model-tier-b.trust-policy.v2.8", "mode": "keyless", "certificate_oidc_issuer": "https://token.actions.githubusercontent.com", "certificate_identity": "https://github.com/acme/butler/.github/workflows/release.yml@refs/heads/main", "repository": "https://github.com/acme/butler", "workflow": ".github/workflows/release.yml", "ref": "refs/heads/main", "commit_sha": "1" * 40, "subject_name": "release.tar.gz", "subject_sha256": SHA, "trusted_root_source": "organization-approved-tuf-root", "expiry_utc": "2030-01-01T00:00:00Z"}


def _keyless_claims(trust: dict[str, Any]) -> dict[str, Any]:
    return {"issuer": trust["certificate_oidc_issuer"], "identity": trust["certificate_identity"], "repository": trust["repository"], "workflow": trust["workflow"], "ref": trust["ref"], "commit_sha": trust["commit_sha"], "subject_name": trust["subject_name"], "subject_sha256": trust["subject_sha256"], "transparency_log_verified": True}


def _statement(trust: dict[str, Any], subject_sha: str) -> dict[str, Any]:
    return {"_type": "https://in-toto.io/Statement/v1", "subject": [{"name": "release.tar.gz", "digest": {"sha256": subject_sha}}], "predicateType": "https://butler.local/attestation/release/v2.8", "predicate": {"repository": trust["repository"], "workflow": trust["workflow"], "ref": trust["ref"], "commit_sha": trust["commit_sha"], "policy_sha256": "2" * 64, "ci_artifact_sha256": "3" * 64}}


def _schedule_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    fixtures = {"schema_version": "butler.model-tier-b.fixture-manifest.v2.8", "fixtures": [{"fixture_id": "fx", "task_id": "task", "input_sha256": SHA, "reference_sha256": SHA_B}]}
    fixtures["fixture_manifest_sha256"] = canonical_sha256(fixtures)
    policy = _approved_policy(); policy["fixture_manifest_sha256"] = fixtures["fixture_manifest_sha256"]; policy["_payload_sha256"] = "f" * 64
    return policy, fixtures


def _environment_receipt() -> dict[str, Any]:
    return {"schema_version": "butler.model-tier-b.environment.v2.8", "platform": "macOS", "chip": "Apple M3 Max", "physical_memory_bytes": 1_000_000, "processor_count": 16, "active_processor_count": 16, "thermal_pre": "nominal", "thermal_post": "nominal", "low_power_mode": False, "power_source": "AC Power", "battery_state": "charging", "metal_registry_id": 1, "macos_build": "25A", "xcode_build": "17A", "background_process_policy_sha256": SHA, "forbidden_process_count": 0}


class AttackMatrixCompletenessTests(unittest.TestCase):
    def test_matrix_exactly_sixty_three_and_all_must_block(self) -> None:
        self.assertEqual(63, len(MATRIX_ROWS))
        self.assertEqual([f"ATK-{index:03d}" for index in range(1, 64)], sorted(MATRIX_ROWS))
        self.assertTrue(all(row["must_block"] == "YES" for row in MATRIX_ROWS.values()))


def _make_attack_test(case_id: str) -> Callable[[unittest.TestCase], None]:
    def test(self: unittest.TestCase) -> None:
        exit_code, fail_class = run_case(case_id)
        row = MATRIX_ROWS[case_id]
        self.assertNotEqual(0, exit_code)
        self.assertEqual(row["expected_fail_class"], fail_class)
    return test


class AttackMatrixTests(unittest.TestCase):
    pass


for _case_id in sorted(MATRIX_ROWS):
    setattr(AttackMatrixTests, f"test_{_case_id.replace('-', '_')}", _make_attack_test(_case_id))
