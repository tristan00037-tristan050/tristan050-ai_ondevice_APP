from __future__ import annotations
from datetime import datetime, timezone

def sample_linux_telemetry() -> dict:
    return {
        "schema_version": "ip3.telemetry.v1.3.1",
        "collected_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id_digest": "a" * 64,
        "evidence": {"class": "sample", "tier": "sample", "source": "deterministic_replay", "physical_device_assertion": False},
        "platform": {"normalized": "linux", "system": "Linux", "release_digest": "b" * 64},
        "privacy": {"raw_device_id_recorded": False, "raw_hostname_recorded": False, "raw_ip_recorded": False, "raw_prompt_recorded": False, "raw_user_text_recorded": False, "raw_log_recorded": False, "raw_path_recorded": False},
        "measurements": {
            "cpu": {"status": "ok", "source": "sample", "logical_processors": 8},
            "memory": {"status": "ok", "source": "sample", "total_bytes": 16 * 1024 ** 3},
            "battery": {"status": "limited", "source": "sample", "battery_present": False, "reason": "desktop_or_ci"},
            "thermal": {"status": "limited", "source": "sample", "thermal_state": "nominal", "reason": "not_exposed"},
            "network": {"status": "ok", "source": "sample", "network_available": True, "hostname_digest": "c" * 64}
        },
        "collector": {"name": "sample_telemetry", "version": "1.3.2", "platform_override_used": False},
        "environment": {"runner": "sample", "containerized": True},
        "source_integrity": {"payload_canonical_sha256": None}
    }
