from __future__ import annotations
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import claim_guard


def write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")

STATE = {
    "approval_status": "NOT_CLAIMED",
    "operational_full_claimed": False,
    "production_hook_deployed": False,
    "physical_lab_claimed": False,
    "production_claimed": False,
    "all_platform_strict_pass_claimed": False,
    "product_candidate_full_replay_claimed": False,
    "live_app_hook_deployed": False,
    "ip2_pep_live_bridge_deployed": False,
    "local_1_7b_forward_verified": False,
    "release_claim_allowed": False,
    "windows_telemetry_validated_by_class": {"ci_lab": False, "vm_lab": False, "physical_lab": False, "production": False},
}
TAXONOMY = {"classes": {"ci_lab": {}, "vm_lab": {}, "physical_lab": {}, "production": {}}, "tiers": {}}


def call_guard(root: Path) -> tuple[int, str, str]:
    old_argv = sys.argv[:]
    out, err = io.StringIO(), io.StringIO()
    try:
        sys.argv = [str(ROOT / "tools" / "claim_guard.py"), str(root)]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = claim_guard.main()
    finally:
        sys.argv = old_argv
    return int(code), out.getvalue(), err.getvalue()

class ClaimGuardTests(unittest.TestCase):
    def test_base_state_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root / "evidence" / "v1_3_ci_lab_state.json", STATE)
            write(root / "evidence" / "evidence_class_taxonomy.json", TAXONOMY)
            code, stdout, stderr = call_guard(root)
            self.assertEqual(code, 0, stderr)
            self.assertIn("CLAIM_GUARD_OK", stdout)

    def test_physical_claim_without_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = dict(STATE)
            bad["windows_telemetry_validated_by_class"] = {"physical_lab": True}
            write(root / "evidence" / "v1_3_ci_lab_state.json", bad)
            write(root / "evidence" / "evidence_class_taxonomy.json", TAXONOMY)
            code, stdout, stderr = call_guard(root)
            self.assertNotEqual(code, 0)
            self.assertIn("physical_lab", stderr)

if __name__ == "__main__":
    unittest.main()
