from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from butler_bench.artifact_scanner import scan_artifact_tree
from butler_bench.attestation import TrustPolicy, verify_in_toto_statement, verify_keyless_claims
from butler_bench.canonical import canonical_sha256, sha256_file, write_canonical_json
from butler_bench.dual_resident import validate_dual_resident
from butler_bench.egress import validate_egress_receipt
from butler_bench.energy import validate_energy_receipt
from butler_bench.evidence import EvidenceWriter, build_artifact_manifest, verify_evidence_directory
from butler_bench.governance import build_final_status
from butler_bench.independence import assert_offline_verifier_independent
from butler_bench.live_verifier import LiveSemanticVerifier
from butler_bench.memory import validate_environment_receipt, validate_memory_receipt
from butler_bench.model_manifest import ModelIdentityGuard, build_model_manifest, verify_model_manifest
from butler_bench.policy import load_approved_policy
from butler_bench.preflight import GATE_NAMES
from butler_bench.schedule import build_schedule, verify_metrics_rows
from butler_bench.terminal_gate import Stage, TerminalDecisionMachine, verify_terminal_evidence
from butler_bench.volatile_draft import DraftState, VolatileDraft
from butler_bench.worker_protocol import verify_worker_stream

from test_attack_matrix_v28 import (
    SHA, SHA_B, _approved_policy, _dual_attack, _environment_receipt,
    _keyless_claims, _memory_attack, _scanner_policy, _schedule_inputs,
    _statement, _trust_policy, _worker_fixture,
)

ROOT = Path(__file__).resolve().parents[1]


class CanonicalPolicyTests(unittest.TestCase):
    def test_approved_policy_is_digest_bound_and_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            policy = _approved_policy(); write_canonical_json(path, policy)
            receipt = load_approved_policy(path, expected_sha256=canonical_sha256(policy), now=datetime(2026, 7, 14, tzinfo=timezone.utc))
            self.assertEqual(100_000, receipt.normalized["max_repair_rate_ppm"])
            self.assertEqual(("task",), tuple(receipt.normalized["task_ids"]))


class IdentityWorkerTests(unittest.TestCase):
    def test_model_manifest_pre_post_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text("{}", encoding="utf-8")
            (root / "tokenizer.json").write_text("{}", encoding="utf-8")
            (root / "weights.bin").write_bytes(b"weights")
            manifest = build_model_manifest(root, metadata_sha256=SHA, variant_id="model-A")
            self.assertEqual(manifest["model_manifest_sha256"], verify_model_manifest(root, manifest))
            guard = ModelIdentityGuard(root, manifest)
            self.assertEqual(guard.verify_pre_generation(), guard.verify_post_generation())

    def test_worker_parent_observed_contract(self) -> None:
        stdout, expected, arrivals = _worker_fixture()
        result = verify_worker_stream(stdout, b"", 0, expected=expected, parent_event_arrival_ns=arrivals, parent_pipe_write_complete_ns=150, parent_eof_ns=1000)
        self.assertEqual(7, result["event_count"])
        self.assertGreater(result["parent_observed_ttft_ns"], 0)


class ScheduleAndTerminalTests(unittest.TestCase):
    def test_balanced_schedule_and_exact_metric_rows(self) -> None:
        policy, fixtures = _schedule_inputs(); schedule = build_schedule(policy, fixtures)
        self.assertEqual(40, len(schedule["rows"]))
        metrics = [dict(row) for row in schedule["rows"] if row["phase"] == "measured"]
        verify_metrics_rows(metrics, schedule)
        self.assertEqual(20, len(metrics))

    def test_single_terminal_and_volatile_draft(self) -> None:
        machine = TerminalDecisionMachine()
        machine.advance(Stage.IDENTITY_VALIDATED); machine.advance(Stage.GENERATION_DONE); machine.advance(Stage.PROVISIONAL_QUALITY_DECIDED)
        machine.record_grounding(True); machine.record_dlp(True); machine.record_approval(True)
        verdict = machine.pass_final().as_dict(); events = [dict(item) for item in machine.safe_events]
        verify_terminal_evidence(events, verdict)
        raw = bytearray(b"ephemeral")
        draft = VolatileDraft(raw, bytes.fromhex(SHA))
        observed = draft.consume_into(bytes.fromhex(SHA), draft.draft_sha256, lambda view: len(view))
        self.assertEqual(9, observed); self.assertEqual(DraftState.DESTROYED, draft.state); self.assertFalse(any(raw))


class EnvironmentSecurityTests(unittest.TestCase):
    def test_memory_environment_and_zero_initial_metal(self) -> None:
        validate_environment_receipt(_environment_receipt(), target={"minimum_physical_memory_bytes": 1})
        # Reuse the happy receipt built by the attack helper, but call the validator directly.
        policy = {"peak_rss_limit_bytes": 10_000, "available_memory_floor_bytes": 100, "sampler_interval_ms": 10, "max_missed_sample_ratio_ppm": 0, "require_metal": True}
        marks = []
        from butler_bench.memory import MEMORY_MARKS
        for index, name in enumerate(MEMORY_MARKS, 1):
            marks.append({"mark": name, "monotonic_ns": index, "target_pid_set": [101], "rss_bytes_total": 1000, "available_memory_bytes": 5000, "memory_pressure": "normal", "sample_source": "approved_sampler", "sample_interval_ms": 10, "missed_sample_count": 0, "sample_count": 10, "max_observed_gap_ms": 10, "metal_current_allocated_size_bytes": 0 if index == 1 else 100, "metal_recommended_max_working_set_size_bytes": 5000, "metal_unsupported_reason": None})
        receipt = {"schema_version": "butler.model-tier-b.memory.v2.8", "sampler_binary_sha256": SHA, "sampler_config_sha256": SHA_B, "sampler_process_pid": 99, "raw_samples_sha256": "c" * 64, "marks": marks, "sampler_error_count": 0}
        validate_memory_receipt(receipt, policy=policy, expected_pid_set=[101], approved_sampler_binary_sha256=SHA, approved_sampler_config_sha256=SHA_B)

    def test_scanner_safe_closed_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "safe.json").write_text('{"fixture_id":"fx","count":1}\n', encoding="utf-8")
            manifest = build_artifact_manifest(root)
            result = scan_artifact_tree(root, manifest, _scanner_policy())
            self.assertTrue(result["raw_zero_pass"])

    def test_verified_and_not_measured_energy_modes(self) -> None:
        measured = {"schema_version": "butler.model-tier-b.energy.v2.8", "status": "MEASURED", "reason": None, "measurement_source": "APPROVED_HARDWARE_METER", "source_binary_sha256": SHA, "unit": "microjoule", "interval_start_ns": 10, "interval_end_ns": 20, "energy_microjoules": 100}
        self.assertEqual("MEASURED", validate_energy_receipt(measured, energy_required=True, run_start_ns=10, run_end_ns=20))
        missing = {"schema_version": "butler.model-tier-b.energy.v2.8", "status": "NOT_MEASURED", "reason": "approved optional metric", "measurement_source": None, "source_binary_sha256": None, "unit": None, "interval_start_ns": None, "interval_end_ns": None, "energy_microjoules": None}
        self.assertEqual("NOT_MEASURED", validate_energy_receipt(missing, energy_required=False, run_start_ns=10, run_end_ns=20))


class TrustEvidenceTests(unittest.TestCase):
    def test_keyless_claims_and_statement_subject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); payload = root / "release.tar.gz"; payload.write_bytes(b"release")
            trust = _trust_policy(); trust["subject_sha256"] = sha256_file(payload)
            policy = TrustPolicy(trust, canonical_sha256(trust))
            verify_keyless_claims(_keyless_claims(trust), policy)
            statement = root / "statement.json"; write_canonical_json(statement, _statement(trust, trust["subject_sha256"]))
            self.assertEqual(64, len(verify_in_toto_statement(statement, payload, policy)))

    def test_complete_receipt_dag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); receipt_root = root / "receipts"; writer = EvidenceWriter(receipt_root, "run")
            mandatory = ["source_provenance", "environment", "benchmark_policy", "model_identity_A", "model_identity_B", "runtime_config_A", "runtime_config_B", "fixture_manifest", "schedule", "worker_event_stream_index", "cold_worker", "live_semantic_verify", "epoch", "dual_resident", "os_egress", "ci", "raw_scan", "final_verdict"]
            parent: list[str] = []
            for receipt_type in mandatory:
                _, digest = writer.write_receipt(receipt_type, subject=[{"name": receipt_type, "sha256": SHA}], parents=parent, payload={"count": 1})
                parent = [digest]
            pointer = f"receipts/{parent[0]}.json"; (root / "final_receipt_path.txt").write_text(pointer + "\n", encoding="ascii")
            profile = {"profile_version": "v2.8", "mandatory_receipts": mandatory, "final_pointer": pointer, "max_receipts": 100}
            result = verify_evidence_directory(root, profile)
            self.assertEqual(18, result["receipt_count"])

    def test_independent_verifier_has_no_producer_import(self) -> None:
        assert_offline_verifier_independent(ROOT / "offline_verifier" / "verify.py")

    def test_blocked_status_cannot_claim_m3_or_g1(self) -> None:
        gates = {name: {"value": False, "receipt_sha256": SHA} for name in GATE_NAMES}
        result = build_final_status(gate_receipts=gates, status="SPEC_READY")
        self.assertEqual("SPEC_READY", result["status"])

    def test_code_delivery_offline_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); status_dir = root / "evidence" / "local_validation"; status_dir.mkdir(parents=True)
            gates = {name: {"value": False, "receipt_sha256": SHA} for name in GATE_NAMES}
            write_canonical_json(status_dir / "final_status.json", build_final_status(gate_receipts=gates, status="SPEC_READY"))
            build_artifact_manifest(root)
            completed = subprocess.run([sys.executable, str(ROOT / "offline_verifier" / "verify.py"), str(root), "--mode", "code-delivery"], capture_output=True, text=True, check=False)
            self.assertEqual(0, completed.returncode, completed.stdout)
            self.assertIn("NO_M3_CLAIM", completed.stdout)


if __name__ == "__main__":
    unittest.main()
