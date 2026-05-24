from __future__ import annotations

from copy import deepcopy
from typing import Literal

OSName = Literal["windows", "darwin", "linux"]

PRIVACY_FLAGS = {
    "raw_device_id_recorded": False,
    "raw_hostname_recorded": False,
    "raw_ip_recorded": False,
    "raw_prompt_recorded": False,
    "raw_user_text_recorded": False,
    "raw_log_recorded": False,
    "raw_path_recorded": False,
}


def make_sample_telemetry(os_name: OSName, battery_source: str = "unavailable", evidence_class: str = "sample") -> dict:
    return {
        "schema_version": "ip3.device_telemetry.v1.3.2",
        "evidence_class": evidence_class,
        "os": os_name,
        "cpu": {"usage_percent": 0.0},
        "memory": {"used_mb": 0, "available_mb": 0},
        "battery": {"present": False, "percent": None, "charging": None, "source": battery_source},
        "thermal": {"cpu_celsius": None, "gpu_celsius": None, "source": "unavailable"},
        "network": {"online": False, "bandwidth_mbps": None},
        "privacy_flags": deepcopy(PRIVACY_FLAGS),
        "otel_units": {
            "system.cpu.utilization": "1",
            "system.memory.usage": "By",
            "system.network.io": "By"
        }
    }


def assert_privacy_flags_false(telemetry: dict) -> None:
    flags = telemetry.get("privacy_flags", {})
    for key, expected in PRIVACY_FLAGS.items():
        if flags.get(key) is not expected:
            raise ValueError(f"privacy flag must be false: {key}")
