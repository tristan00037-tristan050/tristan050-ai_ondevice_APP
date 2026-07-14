from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .canonical import canonical_sha256, read_json_closed, sha256_file
from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@:/_.+-]{2,255}$")
_TOP_LEVEL = {
    "schema_version", "approval_status", "approver_identity", "approval_expiry_utc",
    "fixture_manifest_sha256", "candidates", "quality_floor_by_task",
    "quality_noninferiority_margin_by_task", "ttft_slo_ms_by_task",
    "p95_e2e_slo_ms_by_task", "peak_rss_limit_bytes", "available_memory_floor_bytes",
    "max_repair_rate", "max_cascade_rate", "worker_deadline_seconds",
    "min_co_residency_seconds", "sampler_interval_ms", "max_missed_sample_ratio",
    "tokenizer_manifest_sha256", "bootstrap_seed", "bootstrap_iterations", "energy_required",
}
_CANDIDATE_KEYS = {"variant_id", "model_manifest_sha256", "runtime_config_sha256"}


@dataclass(frozen=True, slots=True)
class PolicyReceipt:
    file_sha256: str
    canonical_sha256: str
    normalized: Mapping[str, Any]


def load_approved_policy(
    path: Path,
    *,
    expected_sha256: str,
    now: datetime | None = None,
) -> PolicyReceipt:
    """Load the canonical JSON policy and fail closed on every ambiguity.

    Decimal fractions are represented as JSON strings and normalized to ppm for
    arithmetic.  This is a stricter RFC 8785 profile that avoids cross-runtime
    binary-float spelling differences.
    """

    if not _SHA256.fullmatch(expected_sha256):
        _block("EXPECTED_POLICY_DIGEST")
    try:
        raw = read_json_closed(path)
    except GateError:
        _block("POLICY_JSON_PARSE_OR_DUPLICATE")
    if not isinstance(raw, dict) or set(raw) != _TOP_LEVEL:
        _block("POLICY_KEYS")
    if _contains_forbidden(raw):
        _block("UNSET_OR_WILDCARD")
    if raw["schema_version"] != "butler.model-tier-b.benchmark-policy.v2.8":
        _block("POLICY_VERSION")
    if raw["approval_status"] != "APPROVED":
        _block("POLICY_NOT_APPROVED")
    identity = raw["approver_identity"]
    if not isinstance(identity, str) or not _IDENTITY.fullmatch(identity):
        _block("APPROVER_IDENTITY")
    _validate_expiry(raw["approval_expiry_utc"], now=now)
    _require_sha(raw["fixture_manifest_sha256"], "FIXTURE_MANIFEST")
    _require_sha(raw["tokenizer_manifest_sha256"], "TOKENIZER_MANIFEST")
    _validate_candidates(raw["candidates"])
    task_ids = _validate_task_maps(raw)
    normalized = dict(raw)
    normalized["max_repair_rate_ppm"] = _fraction_ppm(raw["max_repair_rate"], "MAX_REPAIR_RATE")
    normalized["max_cascade_rate_ppm"] = _fraction_ppm(raw["max_cascade_rate"], "MAX_CASCADE_RATE")
    normalized["max_missed_sample_ratio_ppm"] = _fraction_ppm(
        raw["max_missed_sample_ratio"], "MAX_MISSED_SAMPLE_RATIO"
    )
    normalized["task_ids"] = sorted(task_ids)
    _positive_int(raw, "peak_rss_limit_bytes")
    _positive_int(raw, "available_memory_floor_bytes")
    _positive_int(raw, "worker_deadline_seconds")
    _positive_int(raw, "min_co_residency_seconds")
    _positive_int(raw, "sampler_interval_ms")
    if not isinstance(raw["bootstrap_seed"], int) or isinstance(raw["bootstrap_seed"], bool):
        _block("BOOTSTRAP_SEED")
    if not isinstance(raw["bootstrap_iterations"], int) or raw["bootstrap_iterations"] < 1000:
        _block("BOOTSTRAP_ITERATIONS")
    if type(raw["energy_required"]) is not bool:
        _block("ENERGY_REQUIRED_TYPE")
    digest = canonical_sha256(raw)
    if digest != expected_sha256:
        raise GateError(FailClass.POLICY_TRUST, "POLICY_DIGEST_MISMATCH", exit_code=ExitCode.DIGEST)
    return PolicyReceipt(sha256_file(path), digest, MappingProxyType(normalized))


def load_and_validate_policy(path: Path, expected_sha256: str | None = None) -> PolicyReceipt:
    if expected_sha256 is None:
        _block("EXPECTED_POLICY_DIGEST_REQUIRED")
    return load_approved_policy(path, expected_sha256=expected_sha256)


def _validate_expiry(value: object, *, now: datetime | None) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        _block("APPROVAL_EXPIRY_FORMAT")
    try:
        expiry = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _block("APPROVAL_EXPIRY_FORMAT")
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    if expiry <= reference.astimezone(timezone.utc):
        _block("APPROVAL_EXPIRED")


def _validate_candidates(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"A", "B"}:
        _block("CANDIDATE_SET")
    identities: set[tuple[str, str, str]] = set()
    for name in ("A", "B"):
        candidate = value[name]
        if not isinstance(candidate, dict) or set(candidate) != _CANDIDATE_KEYS:
            _block("CANDIDATE_KEYS")
        variant = candidate["variant_id"]
        if not isinstance(variant, str) or not _IDENTITY.fullmatch(variant):
            _block("VARIANT_ID")
        _require_sha(candidate["model_manifest_sha256"], "MODEL_MANIFEST")
        _require_sha(candidate["runtime_config_sha256"], "RUNTIME_CONFIG")
        identities.add((variant, candidate["model_manifest_sha256"], candidate["runtime_config_sha256"]))
    if len(identities) != 2:
        raise GateError(FailClass.POLICY_TRUST, "CANDIDATES_NOT_DISTINCT", exit_code=ExitCode.SCHEMA)


def _validate_task_maps(raw: dict[str, Any]) -> set[str]:
    names = (
        "quality_floor_by_task", "quality_noninferiority_margin_by_task",
        "ttft_slo_ms_by_task", "p95_e2e_slo_ms_by_task",
    )
    expected: set[str] | None = None
    for name in names:
        mapping = raw[name]
        if not isinstance(mapping, dict) or not mapping:
            _block("TASK_MAP_EMPTY")
        keys = set(mapping)
        if expected is None:
            expected = keys
        elif keys != expected:
            _block("TASK_MAP_MISMATCH")
        for task_id, value in mapping.items():
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", task_id):
                _block("TASK_ID")
            if name.endswith("_ms_by_task"):
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    _block("TASK_LATENCY")
            else:
                _fraction_ppm(value, "TASK_THRESHOLD")
    return expected or set()


def _fraction_ppm(value: object, detail: str) -> int:
    if isinstance(value, bool):
        _block(detail)
    if isinstance(value, int):
        if 0 <= value <= 1_000_000:
            return value
        _block(detail)
    if not isinstance(value, str) or not re.fullmatch(r"(?:0(?:\.\d{1,6})?|1(?:\.0{1,6})?)", value):
        _block(detail)
    try:
        scaled = Decimal(value) * 1_000_000
    except InvalidOperation:
        _block(detail)
    if scaled != scaled.to_integral_value():
        _block(detail)
    return int(scaled)


def _positive_int(raw: dict[str, Any], key: str) -> None:
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _block(key.upper())


def _contains_forbidden(value: object) -> bool:
    if isinstance(value, str):
        upper = value.strip().upper()
        return upper == "UNSET" or "*" in value or "?" in value or not value.strip()
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_forbidden(key) or _contains_forbidden(item) for key, item in value.items())
    return False


def _require_sha(value: object, detail: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _block(detail)


def _block(detail: str) -> None:
    raise GateError(FailClass.POLICY_TRUST, detail, exit_code=ExitCode.SCHEMA)
