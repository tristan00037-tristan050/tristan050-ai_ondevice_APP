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


_OBSERVATION_SCHEMA = "butler.model-tier-b.external-observation.v3"
_SIGNER_SEED = bytes(range(1, 33))  # 32-byte deterministic Ed25519 secret seed (test-only)
_EXTERNAL_TYPES = {"environment", "worker_event_stream_index", "cold_worker", "dual_resident", "os_egress", "epoch", "live_semantic_verify"}


class SignedObservationSemanticTests(unittest.TestCase):
    """PR861-R2 P0-006..009: asymmetric, run-bound, per-receipt-digest, recomputed
    semantic verification. Covers ATK-064..069 (all BLOCK) and the happy path."""

    def _build_evidence(self, root: Path, *, duplicate_type: str | None = None):
        order = list(MANDATORY)
        if duplicate_type:
            order.insert(order.index("final_verdict"), duplicate_type)  # 2nd receipt of same type
        writer = EvidenceWriter(root / "receipts", "run")
        parent: list[str] = []
        meta: dict[str, list[dict]] = {}
        for index, receipt_type in enumerate(order):
            path, digest = writer.write_receipt(receipt_type, subject=[{"name": f"{receipt_type}-{index}", "sha256": SHA}], parents=parent, payload={"count": 1})
            parent = [digest]
            meta.setdefault(receipt_type, []).append({"digest": digest, "path": path})
        pointer = f"receipts/{parent[0]}.json"
        (root / "final_receipt_path.txt").write_text(pointer + "\n", encoding="ascii")
        write_canonical_json(root / "artifact_profile.json", {"profile_version": "v2.8", "mandatory_receipts": sorted(set(order)), "final_pointer": pointer, "max_receipts": 100})
        build_artifact_manifest(root)
        return meta

    def _observation(self, verifier, digest, receipt_type, receipt):
        raw = {"stream_digest": SHA, "sample_count": 3}
        return {
            "receipt_sha256": digest,
            "receipt_type": receipt_type,
            "subject_sha256": verifier.digest_bytes(verifier.canonical_bytes(receipt["subject"])),
            "raw_safe_observation": raw,
            "observation_digest": verifier.digest_bytes(verifier.canonical_bytes(raw)),
        }

    def _sign(self, verifier, meta, *, seed=_SIGNER_SEED, run_id="run", tamper=None):
        observations = []
        for receipt_type, entries in meta.items():
            if receipt_type not in _EXTERNAL_TYPES:
                continue
            for info in entries:
                receipt = json.loads(Path(info["path"]).read_text(encoding="utf-8"))
                observations.append(self._observation(verifier, info["digest"], receipt_type, receipt))
        if tamper is not None:
            tamper(observations, meta, verifier)
        public = verifier.ed25519_publickey(seed).hex()
        unsigned = {"schema_version": _OBSERVATION_SCHEMA, "run_id": run_id, "signer_public_key_ed25519": public, "observations": observations}
        signature = verifier.ed25519_sign(seed, verifier.canonical_bytes(unsigned)).hex()
        bundle = dict(unsigned)
        bundle["signature_ed25519"] = signature
        return bundle, public

    def _run(self, root: Path, tmp: Path, bundle: dict, pinned_pub: str):
        bundle_path = tmp / "observation_bundle.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        argv = [sys.executable, str(ROOT / "offline_verifier" / "verify.py"), str(root), "--mode", "m3-evidence",
                "--observation-bundle", str(bundle_path)]
        if pinned_pub is not None:
            argv += ["--expected-signer-public-key", pinned_pub]
        return subprocess.run(argv, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)

    def _assert_blocked(self, completed, detail: str) -> None:
        self.assertNotEqual(0, completed.returncode, completed.stdout)
        verdict = json.loads(completed.stdout)
        self.assertEqual("BLOCKED", verdict["status"])
        self.assertEqual(detail, verdict["detail_id"], completed.stdout)

    def test_signed_external_observation_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve(); root = tmp / "evidence"; root.mkdir()
            verifier = _load_offline_verifier()
            bundle, pub = self._sign(verifier, self._build_evidence(root))
            completed = self._run(root, tmp, bundle, pub)
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            verdict = json.loads(completed.stdout)
            self.assertEqual("M3_SEMANTIC_PASS", verdict["semantic"]["status"])
            self.assertTrue(verdict["semantic"]["semantic_reexecuted"])
            self.assertEqual(1, verdict["m3_evidence_valid"])
            self.assertEqual("M3_EVIDENCE_VALID", verdict["status"])
            self.assertIs(False, verdict["g1_ready"])

    def test_ATK_064_arbitrary_recomputed_digest_block(self) -> None:
        def tamper(obs, meta, v): obs[0]["observation_digest"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve(); root = tmp / "evidence"; root.mkdir()
            verifier = _load_offline_verifier()
            bundle, pub = self._sign(verifier, self._build_evidence(root), tamper=tamper)
            self._assert_blocked(self._run(root, tmp, bundle, pub), "OBSERVATION_DIGEST_MISMATCH")

    def test_ATK_065_run_id_mismatch_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve(); root = tmp / "evidence"; root.mkdir()
            verifier = _load_offline_verifier()
            bundle, pub = self._sign(verifier, self._build_evidence(root), run_id="a-different-run")
            self._assert_blocked(self._run(root, tmp, bundle, pub), "OBSERVATION_RUN_ID_MISMATCH")

    def test_ATK_066_duplicate_type_partial_observation_block(self) -> None:
        def tamper(obs, meta, v):
            obs.pop()  # drop one os_egress observation, leaving its receipt unobserved
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve(); root = tmp / "evidence"; root.mkdir()
            verifier = _load_offline_verifier()
            bundle, pub = self._sign(verifier, self._build_evidence(root, duplicate_type="os_egress"), tamper=tamper)
            self._assert_blocked(self._run(root, tmp, bundle, pub), "MISSING_EXTERNAL_OBSERVATION")

    def test_ATK_067_unpinned_or_untrusted_signer_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve(); root = tmp / "evidence"; root.mkdir()
            verifier = _load_offline_verifier()
            meta = self._build_evidence(root)
            # (a) verifier given no pin at all -> mandatory pin block
            bundle, pub = self._sign(verifier, meta)
            self._assert_blocked(self._run(root, tmp, bundle, None), "SIGNER_PIN_REQUIRED")
            # (b) attacker signs with their own key; verifier pinned to a different key
            attacker, attacker_pub = self._sign(verifier, meta, seed=bytes(range(2, 34)))
            legit_pub = verifier.ed25519_publickey(_SIGNER_SEED).hex()
            self._assert_blocked(self._run(root, tmp, attacker, legit_pub), "OBSERVATION_SIGNER_UNTRUSTED")

    def test_ATK_068_extra_observation_not_in_receipts_block(self) -> None:
        def tamper(obs, meta, v):
            sched = meta["schedule"][0]  # non-external receipt digest
            receipt = json.loads(Path(sched["path"]).read_text(encoding="utf-8"))
            obs.append(self._observation(v, sched["digest"], "schedule", receipt))
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve(); root = tmp / "evidence"; root.mkdir()
            verifier = _load_offline_verifier()
            bundle, pub = self._sign(verifier, self._build_evidence(root), tamper=tamper)
            self._assert_blocked(self._run(root, tmp, bundle, pub), "OBSERVATION_EXTRA_NON_EXTERNAL")

    def test_ATK_069_observation_raw_artifact_digest_mismatch_block(self) -> None:
        def tamper(obs, meta, v):
            obs[0]["raw_safe_observation"] = {"stream_digest": SHA, "sample_count": 99}  # content changed, digest stale
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve(); root = tmp / "evidence"; root.mkdir()
            verifier = _load_offline_verifier()
            bundle, pub = self._sign(verifier, self._build_evidence(root), tamper=tamper)
            self._assert_blocked(self._run(root, tmp, bundle, pub), "OBSERVATION_DIGEST_MISMATCH")

    def test_forged_signature_block(self) -> None:
        def flip(sig): return sig[:-2] + ("00" if sig[-2:] != "00" else "11")
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory).resolve(); root = tmp / "evidence"; root.mkdir()
            verifier = _load_offline_verifier()
            bundle, pub = self._sign(verifier, self._build_evidence(root))
            bundle["signature_ed25519"] = flip(bundle["signature_ed25519"])
            self._assert_blocked(self._run(root, tmp, bundle, pub), "FORGED_OBSERVATION_SIGNATURE")

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


class GovernanceInvariantTests(unittest.TestCase):
    """R2-P0-010 / §13: g1_ready const false, runtime_activation const 0, enforced in code."""

    def test_valid_governance_passes(self) -> None:
        from butler_bench.governance import assert_governance_invariants

        assert_governance_invariants({"g1_ready": False, "m4_ready": False, "runtime_activation_allowed": 0})

    def test_g1_true_and_activation_mutations_block(self) -> None:
        from butler_bench.governance import assert_governance_invariants

        for mutation in ({"g1_ready": True}, {"m4_ready": True}, {"runtime_activation_allowed": 1}):
            with self.assertRaises(GateError) as ctx:
                assert_governance_invariants(mutation)
            self.assertEqual(FailClass.PREFLIGHT, ctx.exception.fail_class)


if __name__ == "__main__":
    unittest.main()
