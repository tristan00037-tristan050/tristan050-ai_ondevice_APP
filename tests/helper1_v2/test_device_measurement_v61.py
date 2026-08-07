from __future__ import annotations

import base64
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from butler_pc_core.helper1.contracts import canonical_json
from butler_pc_core.helper1.measurement import (
    MeasurementError,
    _recompute_device_raw,
    validate_device_measurement_v2,
)

RUN_ID = "protected-run-1"
POLICY = "4" * 64
OBSERVER = b"native-observer-binary"


def _raw(
    *,
    final_bytes: int = 100,
    reverse_network_time: bool = False,
    interface_counters: list[dict[str, object]] | None = None,
) -> bytes:
    value = {
        "schema_version": "butler.helper1.device-raw-bundle.v2",
        "run_id": RUN_ID,
        "run_attempt": 2,
        "device_class": "M3",
        "hardware_model_identifier": "Mac15,7",
        "os_version": "macOS 26.0",
        "os_build": "25A1",
        "source_commit": "1" * 40,
        "source_tree": "2" * 40,
        "observer_name": "native-helper1-observer",
        "observer_version": "1.0.0",
        "observer_binary_sha256": hashlib.sha256(OBSERVER).hexdigest(),
        "measurement_policy_sha256": POLICY,
        "sample_clock": "monotonic_ns",
        "sample_interval_ns": 1_000_000,
        "samples": [
            {"sequence": 1, "phase": "COLD", "monotonic_ns": 1, "latency_ns": 10, "peak_rss_bytes": 20, "thermal_state": "nominal"},
            {"sequence": 2, "phase": "WARM", "monotonic_ns": 2, "latency_ns": 5, "peak_rss_bytes": 20, "thermal_state": "nominal"},
            {"sequence": 3, "phase": "THERMAL", "monotonic_ns": 3, "latency_ns": 5, "peak_rss_bytes": 20, "thermal_state": "nominal"},
        ],
        "network_trace": {
            "interface_counters": interface_counters
            or [{"name": "en0", "baseline_bytes": 100, "final_bytes": final_bytes}],
            "route_snapshot_sha256": "6" * 64,
            "observation_started_ns": 5 if reverse_network_time else 1,
            "observation_finished_ns": 2,
        },
    }
    return canonical_json(value)


def _signed_inputs(raw: bytes) -> tuple[dict[str, object], bytes, bytes, str]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = hashlib.sha256(public).hexdigest()
    recomputed = _recompute_device_raw(raw)
    unsigned = {
        "schema_version": "butler.helper1.device-receipt.v2",
        "key_id": key_id,
        "run_id": RUN_ID,
        "run_attempt": 2,
        "device_class": "M3",
        "hardware_model_identifier": "Mac15,7",
        "os_build": "25A1",
        "source_commit": "1" * 40,
        "source_tree": "2" * 40,
        "observer_binary_sha256": hashlib.sha256(OBSERVER).hexdigest(),
        "measurement_policy_sha256": POLICY,
        "raw_bundle_sha256": hashlib.sha256(raw).hexdigest(),
        "issued_at_epoch_s": 100,
        "expires_at_epoch_s": 200,
    }
    receipt = canonical_json(
        {**unsigned, "signature_b64": base64.b64encode(private.sign(canonical_json(unsigned))).decode("ascii")}
    )
    value = {
        "schema_version": "butler.helper1.device-measurement.v2",
        "run_id": RUN_ID,
        "run_attempt": 2,
        "device_class": "M3",
        "hardware_model_identifier": "Mac15,7",
        "os_version": "macOS 26.0",
        "os_build": "25A1",
        "source_commit": "1" * 40,
        "source_tree": "2" * 40,
        "device_receipt_sha256": hashlib.sha256(receipt).hexdigest(),
        "receipt_key_id": key_id,
        "measurement_policy_sha256": POLICY,
        "observer_name": "native-helper1-observer",
        "observer_version": "1.0.0",
        "observer_binary_sha256": hashlib.sha256(OBSERVER).hexdigest(),
        "sample_clock": "monotonic_ns",
        "sample_interval_ns": 1_000_000,
        "cold_samples": recomputed["cold_samples"],
        "warm_samples": recomputed["warm_samples"],
        "thermal_samples": recomputed["thermal_samples"],
        "network_observation": recomputed["network_observation"],
        "raw_bundle_sha256": hashlib.sha256(raw).hexdigest(),
    }
    return value, receipt, public, key_id


def _validate(value: dict[str, object], raw: bytes, receipt: bytes, public: bytes, key_id: str):
    return validate_device_measurement_v2(
        value,
        expected_device_class="M3",
        expected_source_commit="1" * 40,
        expected_source_tree="2" * 40,
        expected_run_id=RUN_ID,
        expected_run_attempt=2,
        raw_bundle=raw,
        device_receipt=receipt,
        observer_binary=OBSERVER,
        public_key_bytes=public,
        expected_key_id=key_id,
        expected_policy_sha256=POLICY,
        now_epoch_s=150,
    )


def test_signed_raw_measurement_recomputes_and_rejects_network_egress() -> None:
    raw = _raw()
    value, receipt, public, key_id = _signed_inputs(raw)
    assert _validate(value, raw, receipt, public, key_id)["network_observation"]["delta_bytes"] == 0

    nonzero = _raw(final_bytes=101)
    changed, changed_receipt, changed_public, changed_key = _signed_inputs(nonzero)
    with pytest.raises(MeasurementError, match="NETWORK_EGRESS_NONZERO"):
        _validate(changed, nonzero, changed_receipt, changed_public, changed_key)


def test_fabricated_metadata_unsigned_receipt_and_time_reversal_fail_closed() -> None:
    raw = _raw()
    value, receipt, public, key_id = _signed_inputs(raw)
    value["cold_samples"] = [{"latency_ns": 999, "peak_rss_bytes": 20}]
    with pytest.raises(MeasurementError, match="RAW_SAMPLE_MISMATCH"):
        _validate(value, raw, receipt, public, key_id)

    value, receipt, public, key_id = _signed_inputs(raw)
    tampered_receipt = receipt.replace(b'"signature_b64":"', b'"signature_b64":"A', 1)
    value["device_receipt_sha256"] = hashlib.sha256(tampered_receipt).hexdigest()
    with pytest.raises(MeasurementError, match="MEASUREMENT_SIGNATURE_INVALID"):
        _validate(value, raw, tampered_receipt, public, key_id)

    with pytest.raises(MeasurementError, match="RAW_SAMPLE_MISMATCH"):
        _recompute_device_raw(_raw(reverse_network_time=True))


def test_unconfigured_production_trust_policy_cannot_accept_ephemeral_key() -> None:
    raw = _raw()
    value, receipt, _public, key_id = _signed_inputs(raw)
    with pytest.raises(MeasurementError, match="MEASUREMENT_TRUST_ROOT_INVALID"):
        _validate(value, raw, receipt, b"\x00" * 32, key_id)


def test_interface_counter_increase_and_decrease_cannot_cancel() -> None:
    raw = _raw(
        interface_counters=[
            {"name": "en0", "baseline_bytes": 100, "final_bytes": 110},
            {"name": "en1", "baseline_bytes": 100, "final_bytes": 90},
        ]
    )
    with pytest.raises(MeasurementError, match="NETWORK_COUNTER_RESET_OR_WRAP"):
        _recompute_device_raw(raw)


def test_measurement_cli_uses_protected_policy_not_measurement_self_claim(
    tmp_path: Path,
) -> None:
    raw = _raw()
    value, receipt, public, key_id = _signed_inputs(raw)
    files = {
        "native.json": canonical_json(value),
        "raw.json": raw,
        "receipt.json": receipt,
        "observer.bin": OBSERVER,
        "trust.json": canonical_json(
            {
                "schema_version": "butler.helper1.device-trust-policy.v1",
                "enabled": True,
                "key_id": key_id,
                "public_key_b64": base64.b64encode(public).decode("ascii"),
                "measurement_policy_sha256": "9" * 64,
            }
        ),
    }
    for name, payload in files.items():
        (tmp_path / name).write_bytes(payload)
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ci/helper1_measure_device.py",
            "--device-class",
            "M3",
            "--source-commit",
            "1" * 40,
            "--source-tree",
            "2" * 40,
            "--run-id",
            RUN_ID,
            "--run-attempt",
            "2",
            "--native-measurement",
            str(tmp_path / "native.json"),
            "--raw-bundle",
            str(tmp_path / "raw.json"),
            "--device-receipt",
            str(tmp_path / "receipt.json"),
            "--observer-binary",
            str(tmp_path / "observer.bin"),
            "--trust-policy",
            str(tmp_path / "trust.json"),
            "--output",
            str(tmp_path / "verified.json"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout.splitlines() == [
        "HELPER1_DEVICE_MEASUREMENT_OK=0",
        "ERROR_CODE=MEASUREMENT_TRUST_ROOT_INVALID",
    ]
    assert not (tmp_path / "verified.json").exists()
