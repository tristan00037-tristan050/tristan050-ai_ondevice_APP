from __future__ import annotations
import copy
import hashlib
import json
import tempfile
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ip3.telemetry_schema import SCHEMA_VERSION, compute_payload_canonical_sha256, validate_telemetry_payload, write_json


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sample_payload(platform: str = "windows", evidence_class: str = "ci_lab") -> dict:
    physical = evidence_class == "physical_lab"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "stage": "ip3_v1_3_windows_telemetry_strict_gate",
        "collected_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id_digest": digest("device"),
        "platform": {
            "normalized": platform,
            "python_platform_system": "Windows" if platform == "windows" else platform,
            "python_machine_digest": digest("x64"),
            "python_release_digest": digest("release"),
        },
        "evidence": {
            "class": evidence_class,
            "tier": "real_runtime_measurement",
            "raw_content_stored": False,
            "physical_device_assertion": physical,
        },
        "privacy": {
            "raw_device_id_recorded": False,
            "raw_hostname_recorded": False,
            "raw_ip_recorded": False,
            "raw_prompt_recorded": False,
            "raw_user_text_recorded": False,
            "raw_log_recorded": False,
            "raw_path_recorded": False,
        },
        "environment": {
            "is_ci": evidence_class == "ci_lab",
            "ci_provider": "github_actions" if evidence_class == "ci_lab" else None,
            "ci_provider_digest": digest("github_actions") if evidence_class == "ci_lab" else None,
            "virtualization_detected": False if evidence_class == "physical_lab" else None,
            "virtualization_signal_digest": digest(""),
            "virtualization_signal_count": 0,
            "physical_host_attested": physical,
        },
        "measurements": {
            "cpu": {"status": "ok", "source": "test", "logical_processors": 8, "load_percent": 1.0},
            "memory": {"status": "ok", "source": "test", "total_bytes": 17179869184, "available_bytes": 8589934592, "used_bytes": 8589934592},
            "battery": {"status": "ok", "source": "test", "battery_present": True, "charge_percent": 95},
            "thermal": {"status": "limited", "source": "test", "reason": "fixture_no_sensor"},
            "network": {"status": "ok", "source": "test", "hostname_digest": digest("host"), "address_count": 1, "raw_ip_recorded": False},
        },
        "collector": {"name": "test", "version": "1", "platform_override_used": False, "python_version_digest": digest("py")},
        "source_integrity": {"collector_file_sha256": digest("collector"), "payload_canonical_sha256": None},
    }
    if evidence_class == "ci_lab":
        payload["evidence"]["ci_provider"] = "github_actions"
    payload["source_integrity"]["payload_canonical_sha256"] = compute_payload_canonical_sha256(payload)
    return payload


class TelemetrySchemaTests(unittest.TestCase):
    def test_ci_lab_windows_payload_validates(self) -> None:
        payload = sample_payload("windows", "ci_lab")
        result = validate_telemetry_payload(payload, expected_platform="windows", expected_evidence_class="ci_lab")
        self.assertTrue(result.ok, result.errors)

    def test_ci_lab_cannot_assert_physical_device(self) -> None:
        payload = sample_payload("windows", "ci_lab")
        payload["evidence"]["physical_device_assertion"] = True
        payload["source_integrity"]["payload_canonical_sha256"] = compute_payload_canonical_sha256(payload)
        result = validate_telemetry_payload(payload, expected_platform="windows", expected_evidence_class="ci_lab")
        self.assertFalse(result.ok)
        self.assertTrue(any("physical" in e for e in result.errors))

    def test_physical_lab_requires_physical_controls(self) -> None:
        payload = sample_payload("windows", "physical_lab")
        result = validate_telemetry_payload(payload, expected_platform="windows", expected_evidence_class="physical_lab", require_physical_windows=True, require_battery_present=True)
        self.assertTrue(result.ok, result.errors)
        bad = copy.deepcopy(payload)
        bad["environment"]["virtualization_detected"] = True
        bad["source_integrity"]["payload_canonical_sha256"] = compute_payload_canonical_sha256(bad)
        bad_result = validate_telemetry_payload(bad, expected_platform="windows", expected_evidence_class="physical_lab", require_physical_windows=True, require_battery_present=True)
        self.assertFalse(bad_result.ok)

    def test_windows_and_all_platform_gate_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for platform in ("linux", "darwin", "windows"):
                write_json(root / "evidence" / f"real_telemetry_{platform}.json", sample_payload(platform, "ci_lab"))
            cp = subprocess.run([sys.executable, str(ROOT / "tools" / "windows_real_telemetry_gate.py"), str(root), "--expected-evidence-class", "ci_lab"], text=True, capture_output=True, check=False)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertIn("WINDOWS_REAL_TELEMETRY_OK_CI_LAB", cp.stdout)
            cp2 = subprocess.run([sys.executable, str(ROOT / "tools" / "all_platform_telemetry_gate.py"), str(root), "--require-platforms", "linux,darwin,windows", "--expected-evidence-class", "ci_lab", "--strict"], text=True, capture_output=True, check=False)
            self.assertEqual(cp2.returncode, 0, cp2.stderr)
            self.assertIn("ALL_PLATFORM_TELEMETRY_OK_CI_LAB", cp2.stdout)

if __name__ == "__main__":
    unittest.main()
