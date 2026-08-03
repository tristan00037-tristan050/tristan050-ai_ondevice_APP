#!/usr/bin/env python3
"""Meaning verification for signed Helper1 product-evidence artifacts.

Evidence producers may sign claims, but protected approval is derived from the
referenced bytes and records. Boolean declarations are intentionally rejected.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
RAW_SHA256 = re.compile(r"^[0-9a-f]{64}$")
UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_OBJECT_BYTES = 4 * 1024 * 1024


class EvidenceMeaningError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _exact(value: object, keys: set[str], code: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise EvidenceMeaningError(code)
    return value


def _positive_number(value: object, code: str) -> float:
    if type(value) not in {int, float}:
        raise EvidenceMeaningError(code)
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise EvidenceMeaningError(code)
    return number


def _object_bytes(root: Path, digest: str) -> bytes:
    if SHA256.fullmatch(digest) is None:
        raise EvidenceMeaningError("MEASUREMENT_ARTIFACT_DIGEST_INVALID")
    path = root / "objects" / digest.removeprefix("sha256:")
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or not 0 < info.st_size <= MAX_OBJECT_BYTES:
            raise EvidenceMeaningError("MEASUREMENT_ARTIFACT_OBJECT_INVALID")
        payload = path.read_bytes()
    except OSError as exc:
        raise EvidenceMeaningError("MEASUREMENT_ARTIFACT_OBJECT_INVALID") from exc
    if _sha256(payload) != digest:
        raise EvidenceMeaningError("MEASUREMENT_ARTIFACT_DIGEST_MISMATCH")
    return payload


def _json_object(root: Path, digest: str, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            _object_bytes(root, digest),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise EvidenceMeaningError(code) from exc
    if type(value) is not dict:
        raise EvidenceMeaningError(code)
    return value


def _verify_asset_closure(root: Path, roles: dict[str, str]) -> None:
    base_roles = {"closure_manifest", "consumption_receipt"}
    payload_roles = {name for name in roles if re.fullmatch(r"asset_payload_[0-9]+", name)}
    if not base_roles.issubset(roles) or set(roles) != base_roles | payload_roles or not payload_roles:
        raise EvidenceMeaningError("ASSET_EVIDENCE_ROLES_INVALID")
    manifest = _exact(
        _json_object(root, roles["closure_manifest"], "ASSET_MANIFEST_INVALID"),
        {"schema_version", "files"},
        "ASSET_MANIFEST_INVALID",
    )
    if manifest["schema_version"] != "butler.asset-closure.v1":
        raise EvidenceMeaningError("ASSET_MANIFEST_INVALID")
    files = manifest["files"]
    if type(files) is not dict or not files or len(files) > 100_000:
        raise EvidenceMeaningError("ASSET_MANIFEST_FILES_INVALID")
    expected: dict[str, tuple[int, str, str]] = {}
    for logical_path, record_value in files.items():
        if (
            type(logical_path) is not str
            or not logical_path
            or logical_path.startswith("/")
            or ".." in Path(logical_path).parts
        ):
            raise EvidenceMeaningError("ASSET_LOGICAL_PATH_INVALID")
        record = _exact(
            record_value, {"bytes", "sha256", "artifact_digest"}, "ASSET_RECORD_INVALID"
        )
        if type(record["bytes"]) is not int or record["bytes"] < 1:
            raise EvidenceMeaningError("ASSET_RECORD_INVALID")
        if type(record["sha256"]) is not str or RAW_SHA256.fullmatch(record["sha256"]) is None:
            raise EvidenceMeaningError("ASSET_RECORD_INVALID")
        artifact_digest = record["artifact_digest"]
        if type(artifact_digest) is not str or artifact_digest not in {roles[name] for name in payload_roles}:
            raise EvidenceMeaningError("ASSET_RECORD_INVALID")
        payload = _object_bytes(root, artifact_digest)
        if len(payload) != record["bytes"] or hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise EvidenceMeaningError("ASSET_PAYLOAD_MISMATCH")
        expected[logical_path] = (record["bytes"], record["sha256"], artifact_digest)
    receipt = _exact(
        _json_object(root, roles["consumption_receipt"], "ASSET_RECEIPT_INVALID"),
        {"schema_version", "items"},
        "ASSET_RECEIPT_INVALID",
    )
    if receipt["schema_version"] != "butler.helper1.asset-consumption-set.v1":
        raise EvidenceMeaningError("ASSET_RECEIPT_INVALID")
    items = receipt["items"]
    if type(items) is not list or len(items) != len(expected):
        raise EvidenceMeaningError("ASSET_CONSUMPTION_SET_MISMATCH")
    observed: dict[str, tuple[int, str, str]] = {}
    for item_value in items:
        item = _exact(
            item_value,
            {
                "logical_path",
                "bytes_before",
                "sha256_before",
                "bytes_after",
                "sha256_after",
                "descriptor_only",
                "artifact_digest",
            },
            "ASSET_CONSUMPTION_RECORD_INVALID",
        )
        path = item["logical_path"]
        if (
            type(path) is not str
            or item["descriptor_only"] is not True
            or type(item["bytes_before"]) is not int
            or item["bytes_before"] != item["bytes_after"]
            or item["sha256_before"] != item["sha256_after"]
            or type(item["sha256_before"]) is not str
            or type(item["artifact_digest"]) is not str
            or RAW_SHA256.fullmatch(item["sha256_before"]) is None
        ):
            raise EvidenceMeaningError("ASSET_CONSUMPTION_RECORD_INVALID")
        if path in observed:
            raise EvidenceMeaningError("ASSET_CONSUMPTION_RECORD_DUPLICATE")
        observed[path] = (
            item["bytes_before"], item["sha256_before"], item["artifact_digest"]
        )
    if observed != expected or {item[2] for item in expected.values()} != {roles[name] for name in payload_roles}:
        raise EvidenceMeaningError("ASSET_CONSUMPTION_SET_MISMATCH")


def _verify_e2e(root: Path, roles: dict[str, str]) -> None:
    if set(roles) != {"answer_bytes", "endpoint_trace"}:
        raise EvidenceMeaningError("E2E_EVIDENCE_ROLES_INVALID")
    answer = _object_bytes(root, roles["answer_bytes"])
    trace = _exact(
        _json_object(root, roles["endpoint_trace"], "E2E_TRACE_INVALID"),
        {
            "schema_version",
            "request_id",
            "answer_sha256",
            "events",
            "external_send_records",
            "raw_log_records",
        },
        "E2E_TRACE_INVALID",
    )
    if (
        trace["schema_version"] != "butler.helper1.endpoint-trace.v1"
        or type(trace["request_id"]) is not str
        or UUID.fullmatch(trace["request_id"]) is None
        or trace["answer_sha256"] != _sha256(answer)
        or trace["external_send_records"] != []
        or trace["raw_log_records"] != []
    ):
        raise EvidenceMeaningError("E2E_TRACE_INVALID")
    events = trace["events"]
    required = [
        "asset_lease_opened",
        "model_loaded",
        "endpoint_answered",
        "desktop_signature_verified",
        "answer_displayed",
    ]
    if type(events) is not list or len(events) != len(required):
        raise EvidenceMeaningError("E2E_EVENT_SEQUENCE_INVALID")
    names: list[str] = []
    timestamps: list[int] = []
    for event_value in events:
        event = _exact(event_value, {"name", "monotonic_ns"}, "E2E_EVENT_INVALID")
        if type(event["name"]) is not str or type(event["monotonic_ns"]) is not int:
            raise EvidenceMeaningError("E2E_EVENT_INVALID")
        names.append(event["name"])
        timestamps.append(event["monotonic_ns"])
    if names != required or timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise EvidenceMeaningError("E2E_EVENT_SEQUENCE_INVALID")


def _verify_device_measurement(root: Path, roles: dict[str, str]) -> None:
    if set(roles) != {"device_probe", "measurement_samples"}:
        raise EvidenceMeaningError("DEVICE_EVIDENCE_ROLES_INVALID")
    probe = _exact(
        _json_object(root, roles["device_probe"], "DEVICE_PROBE_INVALID"),
        {"schema_version", "chip", "architecture", "metal_device", "os_build"},
        "DEVICE_PROBE_INVALID",
    )
    if (
        probe["schema_version"] != "butler.helper1.device-probe.v1"
        or probe["chip"] not in {"Apple M3", "Apple M3 Pro", "Apple M3 Max", "Apple M4", "Apple M4 Pro", "Apple M4 Max"}
        or probe["architecture"] != "arm64"
        or type(probe["metal_device"]) is not str
        or not probe["metal_device"].startswith("Apple M")
        or type(probe["os_build"]) is not str
        or not probe["os_build"]
    ):
        raise EvidenceMeaningError("DEVICE_PROBE_INVALID")
    samples = _exact(
        _json_object(root, roles["measurement_samples"], "MEASUREMENT_SAMPLES_INVALID"),
        {"schema_version", "samples"},
        "MEASUREMENT_SAMPLES_INVALID",
    )
    if samples["schema_version"] != "butler.helper1.measurement-samples.v1":
        raise EvidenceMeaningError("MEASUREMENT_SAMPLES_INVALID")
    values = samples["samples"]
    if type(values) is not list or not 100 <= len(values) <= 10_000:
        raise EvidenceMeaningError("MEASUREMENT_SAMPLE_COUNT_INVALID")
    ids: set[str] = set()
    for value in values:
        sample = _exact(
            value,
            {
                "sample_id",
                "latency_ms",
                "memory_peak_bytes",
                "energy_mj",
                "metal_dispatch_count",
                "quality_score",
            },
            "MEASUREMENT_SAMPLE_INVALID",
        )
        sample_id = sample["sample_id"]
        if type(sample_id) is not str or SAFE_ID.fullmatch(sample_id) is None or sample_id in ids:
            raise EvidenceMeaningError("MEASUREMENT_SAMPLE_ID_INVALID")
        ids.add(sample_id)
        _positive_number(sample["latency_ms"], "MEASUREMENT_SAMPLE_INVALID")
        _positive_number(sample["memory_peak_bytes"], "MEASUREMENT_SAMPLE_INVALID")
        _positive_number(sample["energy_mj"], "MEASUREMENT_SAMPLE_INVALID")
        if type(sample["metal_dispatch_count"]) is not int or sample["metal_dispatch_count"] < 1:
            raise EvidenceMeaningError("MEASUREMENT_SAMPLE_INVALID")
        if type(sample["quality_score"]) not in {int, float} or not 0.8 <= float(sample["quality_score"]) <= 1.0:
            raise EvidenceMeaningError("MEASUREMENT_QUALITY_INVALID")


def _verify_sandbox(root: Path, roles: dict[str, str]) -> None:
    if set(roles) != {"denial_records", "sandbox_profile"}:
        raise EvidenceMeaningError("SANDBOX_EVIDENCE_ROLES_INVALID")
    profile = _exact(
        _json_object(root, roles["sandbox_profile"], "SANDBOX_PROFILE_INVALID"),
        {
            "schema_version",
            "app_sandbox",
            "network_client",
            "network_server",
            "temporary_exceptions",
        },
        "SANDBOX_PROFILE_INVALID",
    )
    if (
        profile["schema_version"] != "butler.helper1.sandbox-profile.v1"
        or profile["app_sandbox"] is not True
        or profile["network_client"] is not False
        or profile["network_server"] is not False
        or profile["temporary_exceptions"] != []
    ):
        raise EvidenceMeaningError("SANDBOX_PROFILE_INVALID")
    records = _exact(
        _json_object(root, roles["denial_records"], "SANDBOX_DENIALS_INVALID"),
        {"schema_version", "records"},
        "SANDBOX_DENIALS_INVALID",
    )
    if records["schema_version"] != "butler.helper1.sandbox-denials.v1":
        raise EvidenceMeaningError("SANDBOX_DENIALS_INVALID")
    values = records["records"]
    if type(values) is not list or not 3 <= len(values) <= 10_000:
        raise EvidenceMeaningError("SANDBOX_DENIALS_INVALID")
    categories: set[str] = set()
    sample_ids: set[str] = set()
    timestamps: list[int] = []
    for value in values:
        record = _exact(
            value,
            {"sample_id", "category", "errno", "operation_sha256", "monotonic_ns"},
            "SANDBOX_DENIAL_RECORD_INVALID",
        )
        if (
            type(record["sample_id"]) is not str
            or SAFE_ID.fullmatch(record["sample_id"]) is None
            or record["sample_id"] in sample_ids
            or record["category"] not in {"network", "filesystem", "exec"}
            or record["errno"] not in {"EACCES", "EPERM"}
            or type(record["operation_sha256"]) is not str
            or SHA256.fullmatch(record["operation_sha256"]) is None
            or type(record["monotonic_ns"]) is not int
            or record["monotonic_ns"] < 1
        ):
            raise EvidenceMeaningError("SANDBOX_DENIAL_RECORD_INVALID")
        sample_ids.add(record["sample_id"])
        categories.add(record["category"])
        timestamps.append(record["monotonic_ns"])
    if categories != {"network", "filesystem", "exec"} or timestamps != sorted(timestamps):
        raise EvidenceMeaningError("SANDBOX_DENIAL_COVERAGE_INVALID")


def verify_measurement_artifacts(
    evidence_type: str,
    value: object,
    artifact_digests: object,
    artifact_root: Path,
) -> None:
    if type(value) is not dict:
        raise EvidenceMeaningError("MEASUREMENT_ARTIFACTS_INVALID")
    roles = value
    if (
        not roles
        or any(type(role) is not str or SAFE_ID.fullmatch(role) is None for role in roles)
        or any(type(item) is not str or SHA256.fullmatch(item) is None for item in roles.values())
        or len(set(roles.values())) != len(roles)
        or type(artifact_digests) is not list
        or set(artifact_digests) != set(roles.values())
    ):
        raise EvidenceMeaningError("MEASUREMENT_ARTIFACTS_INVALID")
    verifier = {
        "APPROVED_ASSET_CLOSURE": _verify_asset_closure,
        "REAL_ASSET_E2E_RECEIPT": _verify_e2e,
        "M3_M4_MEASUREMENT": _verify_device_measurement,
        "MACOS_SANDBOX_E2E_RECEIPT": _verify_sandbox,
    }.get(evidence_type)
    if verifier is None:
        raise EvidenceMeaningError("EVIDENCE_TYPE_INVALID")
    verifier(artifact_root, roles)
