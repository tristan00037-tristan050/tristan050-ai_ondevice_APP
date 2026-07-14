"""Repo-level v2.9 P0 fixes: F-004 git blob-in-tree, F-003 structural/semantic split."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from butler_bench.canonical import write_canonical_json
from butler_bench.errors import GateError
from butler_bench.evidence import EvidenceWriter, build_artifact_manifest
from butler_bench.product_bridge import verify_blob_in_commit_tree

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


if __name__ == "__main__":
    unittest.main()
