"""P1: raise critical-path line/branch coverage with happy + mutation cases for
provenance, product_bridge integration evidence, and the owner-runner/verifier
dispatch. Each mutation flips one field and asserts the specific fail-closed block.
"""

from __future__ import annotations

import argparse
import unittest

from butler_bench.canonical import canonical_sha256
from butler_bench.errors import ExitCode, FailClass, GateError
from butler_bench.product_bridge import (
    ADAPTER_ENTRYPOINT,
    REQUIRED_ENTRYPOINTS,
    verify_integration_evidence,
)
from butler_bench.provenance import (
    parse_lfs_pointer,
    reject_git_blob_sha256_confusion,
    validate_full_oid,
    validate_provenance_receipt,
    verify_lfs_materialization,
)

from test_attack_matrix_v28 import SHA, SHA_B, _provenance_receipt


class ProvenanceCoverageTests(unittest.TestCase):
    def test_valid_receipt_passes(self) -> None:
        validate_provenance_receipt(_provenance_receipt())  # no raise

    def _assert_block(self, receipt, detail):
        with self.assertRaises(GateError) as ctx:
            validate_provenance_receipt(receipt)
        self.assertEqual(FailClass.PROVENANCE, ctx.exception.fail_class)
        self.assertIn(detail, str(ctx.exception))

    def test_extra_key_blocks(self) -> None:
        receipt = _provenance_receipt(); receipt["rogue"] = 1
        self._assert_block(receipt, "PROVENANCE_KEYS")

    def test_short_oid_blocks(self) -> None:
        receipt = _provenance_receipt(); receipt["base_commit_oid"] = "abcd"
        with self.assertRaises(GateError):
            validate_provenance_receipt(receipt)

    def test_dirty_tree_blocks(self) -> None:
        receipt = _provenance_receipt(); receipt["clean_tree"] = False
        self._assert_block(receipt, "DIRTY_WORKTREE")

    def test_submodule_mismatch_blocks(self) -> None:
        receipt = _provenance_receipt()
        receipt["submodules"] = [{"path": "s", "url": "u", "commit_oid": "1" * 40, "tree_oid": "2" * 40, "status": "MISMATCH"}]
        self._assert_block(receipt, "SUBMODULE_COMMIT_MISMATCH")

    def test_lfs_materialization_mismatch_blocks(self) -> None:
        receipt = _provenance_receipt()
        receipt["lfs_objects"] = [{"path": "m", "pointer_blob_oid": "1" * 40, "object_sha256": SHA, "materialized_sha256": SHA_B, "size_bytes": 7}]
        self._assert_block(receipt, "LFS_MATERIALIZATION")

    def test_validate_full_oid_variants(self) -> None:
        validate_full_oid("a" * 40, "sha1")
        validate_full_oid("a" * 64, "sha256")
        with self.assertRaises(GateError):
            validate_full_oid("a" * 40, "sha256")
        with self.assertRaises(GateError):
            validate_full_oid("XYZ", "sha1")

    def test_git_blob_sha256_confusion_checks(self) -> None:
        reject_git_blob_sha256_confusion("a" * 40, SHA, "sha1")  # distinct -> no raise
        with self.assertRaises(GateError):
            reject_git_blob_sha256_confusion("a" * 40, "not-a-sha", "sha1")  # invalid file sha256

    def test_parse_and_materialize_lfs_pointer(self) -> None:
        pointer = f"version https://git-lfs.github.com/spec/v1\noid sha256:{SHA}\nsize 7\n".encode("ascii")
        parsed = parse_lfs_pointer(pointer)
        self.assertEqual(SHA, parsed["object_sha256"])
        with self.assertRaises(GateError):
            parse_lfs_pointer(b"not a pointer")
        with self.assertRaises(GateError):
            verify_lfs_materialization(pointer, __import__("pathlib").Path("/nonexistent"))


def _integration_evidence(identity_sha: str) -> dict:
    counts = {name: 1 for name in (*REQUIRED_ENTRYPOINTS, ADAPTER_ENTRYPOINT)}
    evidence = {
        "schema_version": "butler.model-tier-b.actual-integration.v2.8",
        "product_identity_sha256": identity_sha,
        "production_import_path": "butler_pc_core.model_tier_bench.product_adapter",
        "entrypoint_call_counts": counts,
        "production_gate_event_count": len(REQUIRED_ENTRYPOINTS),
        "observer_trace_sha256": SHA,
        "coverage_artifact_sha256": SHA_B,
        "route_diff_sha256": SHA,
        "route_semantics_changed": False,
        "runtime_activation_allowed": 0,
    }
    unsigned = dict(evidence)
    evidence["integration_subject_sha256"] = canonical_sha256(unsigned)
    return evidence


class IntegrationEvidenceCoverageTests(unittest.TestCase):
    def test_valid_integration_evidence_returns_subject(self) -> None:
        identity = SHA
        evidence = _integration_evidence(identity)
        self.assertEqual(evidence["integration_subject_sha256"], verify_integration_evidence(evidence, identity))

    def test_route_semantics_changed_blocks(self) -> None:
        identity = SHA
        evidence = _integration_evidence(identity)
        evidence["route_semantics_changed"] = True
        evidence["integration_subject_sha256"] = canonical_sha256({k: v for k, v in evidence.items() if k != "integration_subject_sha256"})
        with self.assertRaises(GateError) as ctx:
            verify_integration_evidence(evidence, identity)
        self.assertIn("ROUTE_OR_ACTIVATION", str(ctx.exception))

    def test_runtime_activation_nonzero_blocks(self) -> None:
        identity = SHA
        evidence = _integration_evidence(identity)
        evidence["runtime_activation_allowed"] = 1
        evidence["integration_subject_sha256"] = canonical_sha256({k: v for k, v in evidence.items() if k != "integration_subject_sha256"})
        with self.assertRaises(GateError):
            verify_integration_evidence(evidence, identity)

    def test_identity_mismatch_blocks(self) -> None:
        evidence = _integration_evidence(SHA)
        with self.assertRaises(GateError) as ctx:
            verify_integration_evidence(evidence, SHA_B)
        self.assertIn("INTEGRATION_PRODUCT_IDENTITY", str(ctx.exception))

    def test_missing_entrypoint_coverage_blocks(self) -> None:
        identity = SHA
        evidence = _integration_evidence(identity)
        evidence["entrypoint_call_counts"] = {"only": 1}
        evidence["integration_subject_sha256"] = canonical_sha256({k: v for k, v in evidence.items() if k != "integration_subject_sha256"})
        with self.assertRaises(GateError):
            verify_integration_evidence(evidence, identity)

    def test_tampered_subject_digest_blocks(self) -> None:
        identity = SHA
        evidence = _integration_evidence(identity)
        evidence["observer_trace_sha256"] = SHA_B  # change a field without re-signing
        with self.assertRaises(GateError) as ctx:
            verify_integration_evidence(evidence, identity)
        self.assertIn("INTEGRATION_EVIDENCE_DIGEST", str(ctx.exception))


class ProductBridgeBlockBranchTests(unittest.TestCase):
    def test_verify_blob_in_commit_tree_non_git_dir_blocks(self) -> None:
        import tempfile
        from pathlib import Path

        from butler_bench.product_bridge import verify_blob_in_commit_tree

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.py"
            target.write_text("x=1\n", encoding="utf-8")
            with self.assertRaises(GateError):  # not a git worktree
                verify_blob_in_commit_tree(target, "a" * 40)

    def test_validate_product_module_rejects_bad_name_and_identity(self) -> None:
        import tempfile
        from pathlib import Path

        from butler_bench.product_bridge import validate_product_module

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(GateError) as ctx:  # test-prefixed module name
                validate_product_module("tests.evil", approved_product_root=root, expected_module_sha256=SHA, expected_commit_oid="1" * 40)
            self.assertEqual(FailClass.PRODUCT_GATE, ctx.exception.fail_class)
            with self.assertRaises(GateError):  # malformed identity
                validate_product_module("os", approved_product_root=root, expected_module_sha256="short", expected_commit_oid="1" * 40)

    def test_load_product_module_validates_then_imports(self) -> None:
        import tempfile
        from pathlib import Path

        from butler_bench.product_bridge import load_product_module

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(GateError):  # nonexistent module import fails closed
                load_product_module("butler_pc_core_nonexistent_xyz", approved_product_root=Path(directory), expected_module_sha256=SHA, expected_commit_oid="1" * 40)


class OwnerRunnerDispatchTests(unittest.TestCase):
    def test_main_reports_gate_error_exit_code(self) -> None:
        from butler_bench import owner_runner

        original_run, original_parser = owner_runner.run, owner_runner.parser
        owner_runner.parser = lambda: argparse.ArgumentParser()

        def _raise(_args):
            raise GateError(FailClass.PREFLIGHT, "FORCED", exit_code=ExitCode.PROTOCOL)

        try:
            owner_runner.run = _raise
            code = owner_runner.main([])
        finally:
            owner_runner.run, owner_runner.parser = original_run, original_parser
        self.assertEqual(int(ExitCode.PROTOCOL), code)


if __name__ == "__main__":
    unittest.main()
