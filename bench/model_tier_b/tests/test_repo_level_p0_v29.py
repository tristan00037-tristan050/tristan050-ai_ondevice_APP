"""Repo-level v2.9 P0 fixes: F-004 git blob-in-tree, F-003 structural/semantic split."""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from butler_bench.canonical import write_canonical_json
from butler_bench.errors import FailClass, GateError
from butler_bench.evidence import EvidenceWriter, build_artifact_manifest
from butler_bench.product_bridge import verify_blob_in_commit_tree

from entrypoint_owner_attack_kit import build_and_validate
from test_attack_matrix_v28 import SHA

ROOT = Path(__file__).resolve().parents[1]
MANDATORY = [
    "source_provenance", "environment", "benchmark_policy", "model_identity_A", "model_identity_B",
    "runtime_config_A", "runtime_config_B", "fixture_manifest", "schedule", "worker_event_stream_index",
    "cold_worker", "live_semantic_verify", "epoch", "dual_resident", "os_egress", "ci", "raw_scan", "final_verdict",
]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


def _load_offline_verifier():
    spec = importlib.util.spec_from_file_location("offline_verify_under_test", ROOT / "offline_verifier" / "verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BlobInCommitTreeTests(unittest.TestCase):
    """F-004: prove product module blob is actually in the approved commit tree."""

    def _init_repo(self, directory: str) -> Path:
        root = Path(directory).resolve()
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "bench@butler.local")
        _git(root, "config", "user.name", "bench")
        return root

    def test_committed_blob_passes_and_binds_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._init_repo(directory)
            module = root / "product_mod.py"
            module.write_text("__butler_product_commit_oid__ = 'x'\n", encoding="utf-8")
            _git(root, "add", "product_mod.py")
            _git(root, "commit", "-qm", "add product module")
            commit = _git(root, "rev-parse", "HEAD")
            binding = verify_blob_in_commit_tree(module, commit)
            self.assertEqual("product_mod.py", binding["git_toplevel_relative_path"])
            self.assertIn(binding["object_format"], {"sha1", "sha256"})
            self.assertEqual(_git(root, "rev-parse", f"{commit}:product_mod.py"), binding["commit_tree_blob_oid"])

    def test_tampered_file_after_commit_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._init_repo(directory)
            module = root / "product_mod.py"
            module.write_text("original = 1\n", encoding="utf-8")
            _git(root, "add", "product_mod.py")
            _git(root, "commit", "-qm", "c")
            commit = _git(root, "rev-parse", "HEAD")
            module.write_text("tampered = 2\n", encoding="utf-8")  # working tree diverges from commit blob
            with self.assertRaises(GateError) as ctx:
                verify_blob_in_commit_tree(module, commit)
            self.assertIn("PRODUCT_COMMIT_TREE_MISMATCH", str(ctx.exception))

    def test_uncommitted_path_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._init_repo(directory)
            module = root / "product_mod.py"
            module.write_text("x = 1\n", encoding="utf-8")
            _git(root, "commit", "-q", "--allow-empty", "-m", "empty")
            commit = _git(root, "rev-parse", "HEAD")
            with self.assertRaises(GateError) as ctx:  # never added/committed -> not in tree
                verify_blob_in_commit_tree(module, commit)
            self.assertIn("PRODUCT_", str(ctx.exception))


class EntrypointOwnerBindingTests(unittest.TestCase):
    """P0-1 (PR861-F001): every entrypoint owner blob is bound to the commit tree."""

    def test_clean_scenario_passes_and_binds_every_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            identity = build_and_validate(Path(directory), "clean")
            owners = identity["entrypoint_owner_bindings"]
            self.assertTrue(owners)
            for owner in owners:
                self.assertRegex(owner["commit_tree_blob_oid"], r"^[0-9a-f]{40,64}$")

    def test_tampered_owner_after_commit_is_blocked(self) -> None:  # ATK-061
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(GateError) as ctx:
                build_and_validate(Path(directory), "tamper_after_commit")
            self.assertEqual(FailClass.PRODUCT_GATE, ctx.exception.fail_class)
            self.assertIn("PRODUCT_COMMIT_TREE_MISMATCH", str(ctx.exception))

    def test_untracked_owner_file_is_blocked(self) -> None:  # ATK-062
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(GateError) as ctx:
                build_and_validate(Path(directory), "untracked_owner")
            self.assertEqual(FailClass.PRODUCT_GATE, ctx.exception.fail_class)

    def test_runtime_rebound_entrypoint_is_blocked(self) -> None:  # ATK-063
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(GateError) as ctx:
                build_and_validate(Path(directory), "runtime_rebind")
            self.assertEqual(FailClass.PRODUCT_GATE, ctx.exception.fail_class)


class StructuralSemanticSplitTests(unittest.TestCase):
    """F-003: offline verifier reports structural and semantic verdicts separately."""

    def test_semantic_unit_is_fail_closed_without_external_observation(self) -> None:
        verifier = _load_offline_verifier()
        receipts = {
            "a": {"receipt_type": "schedule"},
            "b": {"receipt_type": "dual_resident"},
            "c": {"receipt_type": "os_egress"},
        }
        semantic = verifier.verify_m3_semantic(receipts)
        self.assertEqual("SEMANTIC_REVERIFICATION_UNAVAILABLE", semantic["status"])
        self.assertFalse(semantic["semantic_reexecuted"])
        self.assertIn("dual_resident", semantic["external_observer_required"])
        self.assertIn("os_egress", semantic["external_observer_required"])
        self.assertEqual("STRUCTURE_ONLY_RECHECKED", semantic["receipt_type_results"]["schedule"])

    def _build_evidence_root(self, root: Path) -> None:
        writer = EvidenceWriter(root / "receipts", "run")
        parent: list[str] = []
        for receipt_type in MANDATORY:
            _, digest = writer.write_receipt(receipt_type, subject=[{"name": receipt_type, "sha256": SHA}], parents=parent, payload={"count": 1})
            parent = [digest]
        pointer = f"receipts/{parent[0]}.json"
        (root / "final_receipt_path.txt").write_text(pointer + "\n", encoding="ascii")
        write_canonical_json(root / "artifact_profile.json", {"profile_version": "v2.8", "mandatory_receipts": MANDATORY, "final_pointer": pointer, "max_receipts": 100})
        build_artifact_manifest(root)

    def test_offline_verifier_emits_separated_structural_and_semantic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._build_evidence_root(root)
            completed = subprocess.run(
                [sys.executable, str(ROOT / "offline_verifier" / "verify.py"), str(root), "--mode", "m3-evidence"],
                capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            verdict = json.loads(completed.stdout)
            # Structural PASS is reported...
            self.assertEqual("M3_ARTIFACT_STRUCTURE_PASS", verdict["structural"]["status"])
            self.assertEqual(18, verdict["structural"]["receipt_count"])
            # ...but semantic re-verification is fail-closed, so M3 evidence is NOT valid.
            self.assertEqual("SEMANTIC_REVERIFICATION_UNAVAILABLE", verdict["semantic"]["status"])
            self.assertEqual(0, verdict["m3_evidence_valid"])
            self.assertEqual(0, verdict["runtime_activation_allowed"])


_OBSERVATION_SCHEMA = "butler.model-tier-b.external-observation.v2.9"
_SIGNER_KEY = bytes(range(1, 33))  # 32-byte deterministic test key


class SignedObservationSemanticTests(unittest.TestCase):
    """P0-2 (PR861-F002): signed external observation gives a real semantic PASS path."""

    def _build_evidence(self, root: Path) -> dict[str, dict[str, object]]:
        writer = EvidenceWriter(root / "receipts", "run")
        parent: list[str] = []
        meta: dict[str, dict[str, object]] = {}
        for receipt_type in MANDATORY:
            path, digest = writer.write_receipt(receipt_type, subject=[{"name": receipt_type, "sha256": SHA}], parents=parent, payload={"count": 1})
            parent = [digest]
            meta[receipt_type] = {"digest": digest, "path": path}
        pointer = f"receipts/{parent[0]}.json"
        (root / "final_receipt_path.txt").write_text(pointer + "\n", encoding="ascii")
        write_canonical_json(root / "artifact_profile.json", {"profile_version": "v2.8", "mandatory_receipts": MANDATORY, "final_pointer": pointer, "max_receipts": 100})
        build_artifact_manifest(root)
        return meta

    def _sign_bundle(self, verifier, meta, *, omit=None, wrong_subject_for=None, forge=False):
        observations: dict[str, object] = {}
        for receipt_type, info in meta.items():
            if receipt_type == omit:
                continue
            receipt = json.loads(Path(info["path"]).read_text(encoding="utf-8"))
            subject_sha = verifier.digest_bytes(verifier.canonical_bytes(receipt["subject"]))
            if receipt_type == wrong_subject_for:
                subject_sha = "0" * 64
            observations[receipt_type] = {
                "receipt_sha256": info["digest"],
                "subject_sha256": subject_sha,
                "recomputed_digest": "e" * 64,
                "observation_gap": False,
            }
        key_id = verifier.digest_bytes(_SIGNER_KEY)
        unsigned = {"schema_version": _OBSERVATION_SCHEMA, "run_id": "run", "signer_key_id": key_id, "observations": observations}
        signature = hmac.new(_SIGNER_KEY, verifier.canonical_bytes(unsigned), hashlib.sha256).hexdigest()
        if forge:
            signature = "f" * 64
        bundle = dict(unsigned)
        bundle["observation_signature_hmac_sha256"] = signature
        return bundle, key_id

    def _run_verifier(self, root: Path, tmp: Path, bundle: dict, key_id: str):
        bundle_path = tmp / "observation_bundle.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        key_path = tmp / "signer_key.hex"
        key_path.write_text(_SIGNER_KEY.hex(), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(ROOT / "offline_verifier" / "verify.py"), str(root), "--mode", "m3-evidence",
             "--observation-bundle", str(bundle_path), "--signer-key", str(key_path), "--expected-signer-key-id", key_id],
            capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
        )

    def test_signed_external_observation_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve()
            root = tmp / "evidence"
            root.mkdir()
            meta = self._build_evidence(root)
            verifier = _load_offline_verifier()
            bundle, key_id = self._sign_bundle(verifier, meta)
            completed = self._run_verifier(root, tmp, bundle, key_id)
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            verdict = json.loads(completed.stdout)
            self.assertEqual("M3_SEMANTIC_PASS", verdict["semantic"]["status"])
            self.assertTrue(verdict["semantic"]["semantic_reexecuted"])
            self.assertEqual(1, verdict["m3_evidence_valid"])
            self.assertEqual("M3_EVIDENCE_VALID", verdict["status"])

    def _assert_blocked(self, completed, detail: str) -> None:
        self.assertNotEqual(0, completed.returncode)
        verdict = json.loads(completed.stdout)
        self.assertEqual("BLOCKED", verdict["status"])
        self.assertEqual(detail, verdict["detail_id"])

    def test_missing_external_observation_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve()
            root = tmp / "evidence"; root.mkdir()
            meta = self._build_evidence(root)
            verifier = _load_offline_verifier()
            bundle, key_id = self._sign_bundle(verifier, meta, omit="dual_resident")
            self._assert_blocked(self._run_verifier(root, tmp, bundle, key_id), "MISSING_EXTERNAL_OBSERVATION")

    def test_forged_observation_signature_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve()
            root = tmp / "evidence"; root.mkdir()
            meta = self._build_evidence(root)
            verifier = _load_offline_verifier()
            bundle, key_id = self._sign_bundle(verifier, meta, forge=True)
            self._assert_blocked(self._run_verifier(root, tmp, bundle, key_id), "FORGED_OBSERVATION_SIGNATURE")

    def test_observation_subject_mismatch_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve()
            root = tmp / "evidence"; root.mkdir()
            meta = self._build_evidence(root)
            verifier = _load_offline_verifier()
            bundle, key_id = self._sign_bundle(verifier, meta, wrong_subject_for="os_egress")
            self._assert_blocked(self._run_verifier(root, tmp, bundle, key_id), "OBSERVATION_SUBJECT_MISMATCH")

    def test_semantic_unavailable_forces_nonzero_hold_exit(self) -> None:
        # owner_runner must return an explicit non-zero HOLD, never a silent exit 0,
        # when structure passes but semantics were not re-executed.
        import argparse

        from butler_bench import owner_runner

        original_run, original_parser = owner_runner.run, owner_runner.parser
        owner_runner.parser = lambda: argparse.ArgumentParser()  # bypass required-arg parsing for the exit-code unit
        try:
            owner_runner.run = lambda args: {"status": "M3_ARTIFACT_STRUCTURE_PASS_SEMANTIC_REVIEW_REQUIRED", "m3_evidence_valid": 0, "run_id": "r"}
            code_hold = owner_runner.main([])
            owner_runner.run = lambda args: {"status": "M3_EVIDENCE_VALID", "m3_evidence_valid": 1, "run_id": "r"}
            code_ok = owner_runner.main([])
        finally:
            owner_runner.run, owner_runner.parser = original_run, original_parser
        self.assertEqual(owner_runner.M3_SEMANTIC_HOLD_EXIT, code_hold)
        self.assertNotEqual(0, code_hold)
        self.assertEqual(0, code_ok)


if __name__ == "__main__":
    unittest.main()
