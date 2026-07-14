"""R2-P0-004/005: single real 1.7B owner E2E through the real Box3 product path,
verified by the independent offline verifier (structural AND semantic PASS).

Runs only when the approved model asset is present (owner / M3 machine). In general
CI the model is absent and this test is an EXPLICIT skip — never a mock pass
(§16: TARGET_MODEL_SMOKE=NOT_EXECUTED, TARGET_MODEL_SMOKE_PASS=false).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BENCH_ROOT.parents[1]


def _model_asset_present() -> bool:
    root = os.environ.get("BUTLER_MODEL_ASSET_ROOT")
    rel = os.environ.get("BUTLER_BOX3_1_7B_MODEL_RELATIVE")
    return bool(root and rel and (Path(root) / rel).is_file())


@unittest.skipUnless(
    _model_asset_present(),
    "TARGET_MODEL_ASSET_PRESENT=false: real 1.7B owner E2E is owner/M3-only (explicit skip, not a pass)",
)
class OwnerE2ESmokeTest(unittest.TestCase):
    def test_single_real_owner_e2e_passes_offline_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, str(BENCH_ROOT / "owner_e2e" / "run_owner_e2e.py"), directory],
                capture_output=True, text=True,
                env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
            )
            self.assertEqual(0, completed.returncode, completed.stderr[-2000:])
            result = json.loads(completed.stdout.strip().splitlines()[-1])

            # Owner orchestrator + independent verifier both PASS on the smoke evidence.
            self.assertTrue(result["owner_e2e_pass"])
            self.assertEqual("PASS", result["structural_verify"])
            self.assertEqual("PASS", result["semantic_verify"])
            self.assertEqual(0, result["offline_verifier_exit_code"])
            self.assertTrue(result["smoke_evidence_verifier_pass"])
            # ...but governance M3 validity is NOT auto-promoted by a single smoke.
            self.assertIs(False, result["m3_evidence_valid"])
            self.assertEqual(0, result["m3_smoke_auto_promotion_count"])

            # Single real physical execution on Metal with a first token.
            smoke = result["real_smoke"]
            self.assertEqual("arm64", smoke["architecture"])
            self.assertTrue(smoke["metal_backend_initialized"])
            self.assertGreater(smoke["actual_offloaded_layer_count"], 0)
            self.assertTrue(smoke["first_token_received"])
            self.assertGreaterEqual(smoke["completion_token_count"], 1)
            self.assertRegex(smoke["model_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(1, result["sample_count"])
            self.assertEqual("NOT_PERFORMED", result["performance_comparison"])

            # Real product path stages were called; terminal exactly once.
            for stage in ("grounding_called", "dlp_called", "approval_called", "terminal_gate_called"):
                self.assertTrue(smoke[stage], stage)
            self.assertEqual(1, smoke["terminal_count"])

            # Governance stays fail-closed even on a passing smoke.
            self.assertIs(False, result["g1_ready"])
            self.assertIs(False, result["m4_ready"])
            self.assertEqual(0, result["runtime_activation_allowed"])
            self.assertGreater(result["imported_product_module_count"], 0)


if __name__ == "__main__":
    unittest.main()
