from __future__ import annotations
import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.ip3.bridges import build_ip1_model_registry_from_status, simulate_ip2_pep_contract
from src.ip3.routing_engine import RoutingEngine
from src.ip3.user_context import UserContext
from tools._sample_telemetry import sample_linux_telemetry

class RoutingEngineTests(unittest.TestCase):
    def test_restricted_fails_closed_when_ip1_forward_false(self):
        ctx = UserContext.from_metadata(task_type="analysis", urgency="high", accuracy_requirement="critical", data_sensitivity="Restricted", request_fingerprint_seed="x")
        engine = RoutingEngine(build_ip1_model_registry_from_status({"forward_verified": False}))
        decision = engine.decide(telemetry=sample_linux_telemetry(), context=ctx, ip2_policy_decision=simulate_ip2_pep_contract("Restricted").as_policy_decision())
        self.assertEqual(decision.target, "blocked")
        self.assertIn(decision.routing_state, {"failed_closed", "blocked"})

    def test_public_external_api_disabled(self):
        ctx = UserContext.from_metadata(task_type="admin", urgency="low", accuracy_requirement="medium", data_sensitivity="Public", request_fingerprint_seed="p")
        engine = RoutingEngine(build_ip1_model_registry_from_status({"forward_verified": False}), external_api_enabled=False)
        decision = engine.decide(telemetry=sample_linux_telemetry(), context=ctx, ip2_policy_decision=simulate_ip2_pep_contract("Public").as_policy_decision())
        self.assertNotEqual(decision.target, "external_api")

    def test_ip2_denial_blocks(self):
        ctx = UserContext.from_metadata(task_type="analysis", urgency="normal", accuracy_requirement="high", data_sensitivity="Internal", request_fingerprint_seed="d")
        engine = RoutingEngine(build_ip1_model_registry_from_status({"forward_verified": True, "logits_digest": "f"*64}))
        decision = engine.decide(telemetry=sample_linux_telemetry(), context=ctx, ip2_policy_decision=simulate_ip2_pep_contract("Internal", allow=False).as_policy_decision())
        self.assertEqual(decision.target, "blocked")
        self.assertFalse(decision.policy_allowed)

if __name__ == "__main__":
    unittest.main()
