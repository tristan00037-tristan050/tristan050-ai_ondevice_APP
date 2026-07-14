"""R2-P0-004/005 + R3-P0-A: single real 1.7B owner E2E through the real Box3 product
path, verified by the independent offline verifier against an EXTERNAL SHA-pinned trust
policy signed by an EXTERNAL provisioned key (no committed seed).

Runs only when the approved model asset is present (owner / M3 machine). In general CI
the model is absent and this test is an EXPLICIT skip — never a mock pass.
"""

from __future__ import annotations

import hashlib
import importlib.util
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


def _load_verifier():
    spec = importlib.util.spec_from_file_location("owner_test_verify", BENCH_ROOT / "offline_verifier" / "verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(
    _model_asset_present(),
    "TARGET_MODEL_ASSET_PRESENT=false: real 1.7B owner E2E is owner/M3-only (explicit skip, not a pass)",
)
class OwnerE2ESmokeTest(unittest.TestCase):
    def test_single_real_owner_e2e_passes_with_external_key_and_policy(self) -> None:
        verifier = _load_verifier()
        seed = os.urandom(32)  # ephemeral, per-run, never committed
        pub = verifier.ed25519_publickey(seed).hex()
        approved_id = hashlib.sha256(bytes.fromhex(pub)).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            key_file = base / "signing_key.hex"  # external, outside repo
            key_file.write_text(seed.hex(), encoding="utf-8")
            os.chmod(key_file, 0o600)
            policy = {
                "schema_version": "butler.m3.trust-policy.v1", "policy_id": "test-owner", "policy_version": 1,
                "signature_algorithm": "Ed25519", "public_key_encoding": "hex-raw-32",
                "public_key": pub, "public_key_sha256": approved_id,
                "accepted_key_ids": [approved_id],
                "revoked_key_ids": ["f4d270b771e4589f6d5a78943f5597a0f45d4e9da336a8fb52c23db7f62bcdf3"],
                "payload_type": "application/vnd.butler.m3-observation.v1+json",
            }
            policy_text = json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            policy_file = base / "trust_policy.json"
            policy_file.write_text(policy_text, encoding="utf-8")
            policy_sha = hashlib.sha256(policy_text.encode("utf-8")).hexdigest()
            output = base / "out"

            env = {
                **os.environ,
                "PYTHONPATH": str(REPO_ROOT),
                "BUTLER_BENCH_SIGNING_KEY_FILE": str(key_file),
                "BUTLER_BENCH_TRUST_POLICY": str(policy_file),
                "BUTLER_BENCH_TRUST_POLICY_SHA256": policy_sha,
            }
            completed = subprocess.run(
                [sys.executable, str(BENCH_ROOT / "owner_e2e" / "run_owner_e2e.py"), str(output)],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(0, completed.returncode, completed.stderr[-2000:])
            result = json.loads(completed.stdout.strip().splitlines()[-1])

            # No committed seed; the external provisioned key drove the signature.
            self.assertIs(False, result["committed_signing_seed"])
            self.assertTrue(result["production_signing_key_ready"])

            # Owner orchestrator + independent verifier both PASS (structural + semantic).
            self.assertTrue(result["owner_e2e_pass"])
            self.assertEqual("PASS", result["structural_verify"])
            self.assertEqual("PASS", result["semantic_verify"])
            self.assertEqual(0, result["offline_verifier_exit_code"])

            # Single real physical execution on Metal with a first token.
            smoke = result["real_smoke"]
            self.assertEqual("arm64", smoke["architecture"])
            self.assertTrue(smoke["metal_backend_initialized"])
            self.assertGreater(smoke["actual_offloaded_layer_count"], 0)
            self.assertTrue(smoke["first_token_received"])
            self.assertGreaterEqual(smoke["completion_token_count"], 1)
            self.assertRegex(smoke["model_sha256"], r"^[0-9a-f]{64}$")
            for stage in ("grounding_called", "dlp_called", "approval_called", "terminal_gate_called"):
                self.assertTrue(smoke[stage], stage)
            self.assertEqual(1, smoke["terminal_count"])

            # Governance: even a passing smoke never promotes M3/G1.
            self.assertIs(False, result["m3_evidence_valid"])
            self.assertEqual(0, result["m3_smoke_auto_promotion_count"])
            self.assertIs(False, result["g1_ready"])
            self.assertIs(False, result["m4_ready"])
            self.assertEqual(0, result["runtime_activation_allowed"])

    def test_without_external_key_semantic_is_unavailable_not_pass(self) -> None:
        # No provisioned key => structural-only diagnostic; semantic never PASSes.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            env = {k: v for k, v in os.environ.items() if k not in {"BUTLER_BENCH_SIGNING_KEY_FILE"}}
            env["PYTHONPATH"] = str(REPO_ROOT)
            completed = subprocess.run(
                [sys.executable, str(BENCH_ROOT / "owner_e2e" / "run_owner_e2e.py"), str(output)],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(0, completed.returncode, completed.stderr[-2000:])
            result = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertIs(False, result["production_signing_key_ready"])
            self.assertEqual("UNAVAILABLE_NO_PROVISIONED_KEY", result["semantic_verify"])
            self.assertIs(False, result["m3_evidence_valid"])


if __name__ == "__main__":
    unittest.main()
