from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest

from butler_pc_core.model_tier.contracts import sha256_text
from butler_pc_core.model_tier.device_profiler import (
    _parse_vm_stat_text,
    collect_device_profile,
)
from butler_pc_core.model_tier.routing_audit import (
    ALLOWED_SHADOW_KEYS,
    HashChainJsonlWriter,
    build_shadow_record,
    validate_shadow_record,
)
from butler_pc_core.model_tier.shadow_observer import NonBlockingShadowRecorder


def _record(index: int = 1) -> dict:
    digest = sha256_text(str(index))
    return build_shadow_record(
        timestamp_epoch_ms=index,
        request_digest=digest,
        box_id="3",
        task_profile_digest=digest,
        device_profile_digest=digest,
        policy_digest=digest,
        decision_digest=digest,
        recommended_tier="TIER_1P7B",
        recommended_variant_id="box3_v9_2_r2b_1p7_q4_k_m",
        reason_codes=("BOX3_SPECIALIZED_1P7B_PRIMARY",),
        high_eligible=False,
        gate_reason_code=None,
        would_escalate=False,
        actual_response_digest=digest,
    )


def test_native_profile_and_vm_stat_are_structured_and_nonzero() -> None:
    vm_stat = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free: 10.
Pages active: 999.
Pages inactive: 20.
Pages speculative: 3.
Pages purgeable: 2.
"""
    assert _parse_vm_stat_text(vm_stat) == 35 * 16_384
    profile = collect_device_profile(
        {
            "total_memory_bytes": 64 * 1024**3,
            "available_memory_bytes": 20 * 1024**3,
            "process_rss_bytes": 1024,
            "memory_pressure": "NORMAL",
            "thermal_state": "NOMINAL",
            "low_power_mode": False,
            "battery_percent": 90,
            "metal_available": True,
            "chip_family": "Apple M3 Max",
        }
    )
    assert profile.validity.value == "VALID"
    assert profile.profiler_source == "native_tauri"
    assert profile.raw_text_logged is False


def test_invalid_native_memory_is_not_downgraded_to_unknown() -> None:
    zero = collect_device_profile(
        {"total_memory_bytes": 0, "available_memory_bytes": 0}
    )
    exceeds = collect_device_profile(
        {"total_memory_bytes": 1024, "available_memory_bytes": 2048}
    )
    assert zero.validity.value == "INVALID"
    assert exceeds.validity.value == "INVALID"


def test_audit_exact_keys_hash_chain_modes_and_rotation(tmp_path: Path) -> None:
    path = tmp_path / "audit" / "model_tier_shadow_v1.jsonl"
    writer = HashChainJsonlWriter(path, max_bytes=1600)
    first_digest = writer.append(_record(1))
    for index in range(2, 8):
        writer.append(_record(index))
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.with_name(path.name + ".1").is_file()
    all_rows = []
    for candidate in (path.with_name(path.name + ".1"), path):
        all_rows.extend(
            json.loads(line)
            for line in candidate.read_text(encoding="utf-8").splitlines()
            if line
        )
    assert all(set(row) == ALLOWED_SHADOW_KEYS for row in all_rows)
    assert all(row["raw_text_logged"] is False for row in all_rows)
    assert all(row["external_send_zero"] is True for row in all_rows)
    assert first_digest.startswith("sha256:")
    for row in all_rows:
        validate_shadow_record(row)


def test_audit_rejects_symlink_target(tmp_path: Path) -> None:
    real = tmp_path / "real.jsonl"
    real.write_text("", encoding="utf-8")
    link = tmp_path / "link.jsonl"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="AUDIT_PATH_INVALID"):
        HashChainJsonlWriter(link)


def test_record_requires_exact_allowlisted_keys() -> None:
    record = _record()
    record["raw_text"] = "forbidden"
    record["previous_record_digest"] = sha256_text("previous")
    record["record_digest"] = sha256_text("record")
    with pytest.raises(ValueError, match="EXACT_KEYS"):
        validate_shadow_record(record, verify_record_digest=False)


def test_nonblocking_recorder_submit_budget_and_writer_failure_isolated() -> None:
    class FailingWriter:
        def append(self, _record):
            raise OSError("synthetic")

    recorder = NonBlockingShadowRecorder(FailingWriter(), queue_capacity=8)  # type: ignore[arg-type]
    started = time.perf_counter()
    assert recorder.submit(_record()) is True
    elapsed_ms = (time.perf_counter() - started) * 1000
    deadline = time.monotonic() + 1.0
    while recorder.stats().failures == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    recorder.close()
    assert elapsed_ms < 5.0
    assert recorder.stats().failures == 1
