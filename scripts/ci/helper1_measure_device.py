#!/usr/bin/env python3
"""Validate and publish native Helper1 M3/M4 measurements; never estimate."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.contracts import canonical_json  # noqa: E402
from butler_pc_core.helper1.measurement import MeasurementError, validate_device_measurement_v2  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-class", required=True, choices=("M3", "M4"))
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--native-measurement", required=True, type=Path)
    parser.add_argument("--raw-bundle", required=True, type=Path)
    parser.add_argument("--device-receipt", required=True, type=Path)
    parser.add_argument("--observer-binary", required=True, type=Path)
    parser.add_argument("--trust-policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        raw_bundle = args.raw_bundle.read_bytes()
        device_receipt = args.device_receipt.read_bytes()
        observer_binary = args.observer_binary.read_bytes()
        value = json.loads(
            args.native_measurement.read_bytes(),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        trust = json.loads(
            args.trust_policy.read_bytes(),
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        if (
            type(trust) is not dict
            or set(trust) != {
                "schema_version",
                "enabled",
                "key_id",
                "public_key_b64",
                "measurement_policy_sha256",
            }
            or trust.get("schema_version") != "butler.helper1.device-trust-policy.v1"
            or trust.get("enabled") is not True
            or type(trust.get("key_id")) is not str
            or type(trust.get("public_key_b64")) is not str
            or type(trust.get("measurement_policy_sha256")) is not str
        ):
            raise MeasurementError("MEASUREMENT_TRUST_ROOT_UNCONFIGURED")
        try:
            public_key = base64.b64decode(trust["public_key_b64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise MeasurementError("MEASUREMENT_TRUST_ROOT_INVALID") from exc
        if hashlib.sha256(public_key).hexdigest() != trust["key_id"]:
            raise MeasurementError("MEASUREMENT_TRUST_ROOT_INVALID")
        verified = validate_device_measurement_v2(
            value,
            expected_device_class=args.device_class,
            expected_source_commit=args.source_commit,
            expected_source_tree=args.source_tree,
            expected_run_id=args.run_id,
            expected_run_attempt=args.run_attempt,
            raw_bundle=raw_bundle,
            device_receipt=device_receipt,
            observer_binary=observer_binary,
            public_key_bytes=public_key,
            expected_key_id=trust["key_id"],
            expected_policy_sha256=trust["measurement_policy_sha256"],
            now_epoch_s=int(time.time()),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(canonical_json(verified) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(descriptor)
    except MeasurementError as exc:
        print("HELPER1_DEVICE_MEASUREMENT_OK=0")
        print(f"ERROR_CODE={exc}")
        return 1
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        print("HELPER1_DEVICE_MEASUREMENT_OK=0")
        print("ERROR_CODE=DEVICE_MEASUREMENT_MISSING")
        return 1
    print("HELPER1_DEVICE_MEASUREMENT_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
