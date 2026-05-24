from __future__ import annotations

import hashlib
import json
import platform as py_platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SCHEMA_VERSION = "ip3.telemetry.v1.3.1"
ALLOWED_PLATFORMS = {"linux", "darwin", "windows"}
ALLOWED_EVIDENCE_CLASSES = {"ci_lab", "vm_lab", "physical_lab", "production"}
ALLOWED_EVIDENCE_TIERS = {"real_runtime_measurement", "secure_lab", "sample"}
REQUIRED_DIMENSIONS = ("cpu", "memory", "battery", "thermal", "network")
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PRIVACY_FLAGS_FALSE = (
    "raw_device_id_recorded",
    "raw_hostname_recorded",
    "raw_ip_recorded",
    "raw_prompt_recorded",
    "raw_user_text_recorded",
    "raw_log_recorded",
    "raw_path_recorded",
)

EVIDENCE_CLASS_RANK = {
    "ci_lab": 10,
    "vm_lab": 20,
    "physical_lab": 30,
    "production": 40,
}


def normalize_platform_name(value: str) -> str:
    v = (value or "").strip().lower()
    if v in {"linux", "gnu/linux"}:
        return "linux"
    if v in {"darwin", "macos", "mac", "osx"}:
        return "darwin"
    if v.startswith("win") or v in {"windows", "msys", "cygwin"}:
        return "windows"
    return v


def current_platform_name() -> str:
    return normalize_platform_name(py_platform.system())


def expected_evidence_path(root: Path, platform_name: str) -> Path:
    norm = normalize_platform_name(platform_name)
    return Path(root) / "evidence" / f"real_telemetry_{norm}.json"


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_payload_canonical_sha256(payload: Mapping[str, Any]) -> str:
    copy: Dict[str, Any] = json.loads(json.dumps(payload, ensure_ascii=False))
    integrity = copy.get("source_integrity")
    if isinstance(integrity, MutableMapping):
        integrity["payload_canonical_sha256"] = None
    return hashlib.sha256(canonical_json_bytes(copy)).hexdigest()


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: List[str]
    warnings: List[str]
    platform: Optional[str]
    evidence_class: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "platform": self.platform,
            "evidence_class": self.evidence_class,
        }


def _append_measurement_errors(errors: List[str], dim: str, block: Any, *, strict_core: bool) -> None:
    if not isinstance(block, Mapping):
        errors.append(f"measurements.{dim} must be object")
        return
    status = block.get("status")
    if status not in {"ok", "limited", "unavailable", "failed"}:
        errors.append(f"measurements.{dim}.status invalid: {status!r}")
    if status in {"limited", "unavailable", "failed"} and not block.get("reason"):
        errors.append(f"measurements.{dim}.reason required when status={status!r}")
    if not block.get("source"):
        errors.append(f"measurements.{dim}.source missing")
    if strict_core and dim in {"cpu", "memory", "network"} and status != "ok":
        errors.append(f"measurements.{dim}.status must be ok in strict core telemetry")
    if dim == "cpu" and status == "ok":
        logical = block.get("logical_processors")
        if not isinstance(logical, int) or logical <= 0:
            errors.append("measurements.cpu.logical_processors must be positive int")
    if dim == "memory" and status == "ok":
        total = block.get("total_bytes")
        if not isinstance(total, int) or total <= 0:
            errors.append("measurements.memory.total_bytes must be positive int")
    if dim == "network" and status == "ok":
        if not isinstance(block.get("hostname_digest"), str) or not HEX_SHA256_RE.match(str(block.get("hostname_digest", ""))):
            errors.append("measurements.network.hostname_digest must be sha256 hex digest")


def validate_telemetry_payload(
    payload: Mapping[str, Any],
    *,
    expected_platform: Optional[str] = None,
    expected_evidence_class: Optional[str] = None,
    strict_core: bool = True,
    require_physical_windows: bool = False,
    require_battery_present: bool = False,
    allow_production: bool = False,
) -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []
    platform_name: Optional[str] = None
    evidence_class: Optional[str] = None

    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}, actual={payload.get('schema_version')!r}")

    evidence = payload.get("evidence")
    if not isinstance(evidence, Mapping):
        errors.append("evidence block missing")
    else:
        evidence_class = str(evidence.get("class", ""))
        if evidence_class not in ALLOWED_EVIDENCE_CLASSES:
            errors.append(f"evidence.class invalid: {evidence_class!r}")
        if expected_evidence_class and evidence_class != expected_evidence_class:
            errors.append(f"evidence.class mismatch expected={expected_evidence_class!r} actual={evidence_class!r}")
        if evidence_class == "production" and not allow_production:
            errors.append("evidence.class=production is not allowed in v1.3 lab pack")
        tier = evidence.get("tier")
        if tier not in ALLOWED_EVIDENCE_TIERS:
            errors.append(f"evidence.tier invalid: {tier!r}")
        if evidence_class in {"ci_lab", "vm_lab", "physical_lab"} and tier != "real_runtime_measurement":
            errors.append(f"evidence.tier must be real_runtime_measurement for {evidence_class}")
        if evidence_class == "ci_lab" and not evidence.get("ci_provider"):
            errors.append("evidence.ci_provider required for ci_lab")
        if evidence_class in {"ci_lab", "vm_lab"} and evidence.get("physical_device_assertion") is True:
            errors.append(f"{evidence_class} cannot set physical_device_assertion=true")
        if evidence_class == "physical_lab" and evidence.get("physical_device_assertion") is not True:
            errors.append("physical_lab requires physical_device_assertion=true")

    platform_block = payload.get("platform")
    if not isinstance(platform_block, Mapping):
        errors.append("platform block missing")
    else:
        platform_name = normalize_platform_name(str(platform_block.get("normalized", "")))
        if platform_name not in ALLOWED_PLATFORMS:
            errors.append(f"platform.normalized invalid: {platform_name!r}")
        if expected_platform:
            exp = normalize_platform_name(expected_platform)
            if platform_name != exp:
                errors.append(f"platform mismatch expected={exp!r} actual={platform_name!r}")

    if not isinstance(payload.get("collected_at_utc"), str) or not payload.get("collected_at_utc"):
        errors.append("collected_at_utc missing")

    device_id_digest = payload.get("device_id_digest")
    if not isinstance(device_id_digest, str) or not HEX_SHA256_RE.match(device_id_digest):
        errors.append("device_id_digest must be sha256 hex digest")
    if "device_id" in payload:
        errors.append("raw device_id must not be stored")

    privacy = payload.get("privacy")
    if not isinstance(privacy, Mapping):
        errors.append("privacy block missing")
    else:
        for flag in PRIVACY_FLAGS_FALSE:
            if privacy.get(flag) is not False:
                errors.append(f"privacy.{flag} must be false")

    measurements = payload.get("measurements")
    if not isinstance(measurements, Mapping):
        errors.append("measurements block missing")
    else:
        for dim in REQUIRED_DIMENSIONS:
            if dim not in measurements:
                errors.append(f"measurements.{dim} missing")
            else:
                _append_measurement_errors(errors, dim, measurements[dim], strict_core=strict_core)
        if require_battery_present:
            batt = measurements.get("battery")
            if not isinstance(batt, Mapping) or batt.get("battery_present") is not True or batt.get("status") != "ok":
                errors.append("physical Windows laptop gate requires battery.status=ok and battery_present=true")

    collector = payload.get("collector")
    if not isinstance(collector, Mapping):
        errors.append("collector block missing")
    else:
        if not collector.get("name"):
            errors.append("collector.name missing")
        if not collector.get("version"):
            errors.append("collector.version missing")
        if collector.get("platform_override_used") is not False:
            errors.append("collector.platform_override_used must be false")

    env = payload.get("environment")
    if not isinstance(env, Mapping):
        errors.append("environment block missing")
    else:
        if require_physical_windows:
            if platform_name != "windows":
                errors.append("physical Windows gate requires platform=windows")
            if env.get("is_ci") is not False:
                errors.append("physical Windows gate requires environment.is_ci=false")
            if env.get("virtualization_detected") is True:
                errors.append("physical Windows gate forbids virtualization_detected=true")
            if env.get("physical_host_attested") is not True:
                errors.append("physical Windows gate requires environment.physical_host_attested=true")

    source_integrity = payload.get("source_integrity")
    if not isinstance(source_integrity, Mapping):
        errors.append("source_integrity block missing")
    else:
        digest = source_integrity.get("payload_canonical_sha256")
        if not isinstance(digest, str) or not HEX_SHA256_RE.match(digest):
            errors.append("source_integrity.payload_canonical_sha256 must be sha256 hex digest")
        else:
            actual = compute_payload_canonical_sha256(payload)
            if digest != actual:
                errors.append(f"payload_canonical_sha256 mismatch expected={digest} actual={actual}")
        collector_sha = source_integrity.get("collector_file_sha256")
        if collector_sha is not None and (not isinstance(collector_sha, str) or not HEX_SHA256_RE.match(str(collector_sha))):
            errors.append("source_integrity.collector_file_sha256 must be sha256 hex digest")

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings, platform=platform_name, evidence_class=evidence_class)


def validate_telemetry_file(
    path: Path,
    *,
    expected_platform: Optional[str] = None,
    expected_evidence_class: Optional[str] = None,
    strict_core: bool = True,
    require_physical_windows: bool = False,
    require_battery_present: bool = False,
    allow_production: bool = False,
) -> ValidationResult:
    if not Path(path).exists():
        return ValidationResult(False, [f"missing telemetry file {path}"], [], normalize_platform_name(expected_platform or ""), expected_evidence_class)
    try:
        payload = read_json(Path(path))
    except Exception as exc:
        return ValidationResult(False, [f"failed to read json {path}: {exc}"], [], expected_platform, expected_evidence_class)
    if not isinstance(payload, Mapping):
        return ValidationResult(False, [f"telemetry payload must be object {path}"], [], expected_platform, expected_evidence_class)
    return validate_telemetry_payload(
        payload,
        expected_platform=expected_platform,
        expected_evidence_class=expected_evidence_class,
        strict_core=strict_core,
        require_physical_windows=require_physical_windows,
        require_battery_present=require_battery_present,
        allow_production=allow_production,
    )


def validate_required_platform_files(
    root: Path,
    required_platforms: Sequence[str],
    *,
    expected_class_by_platform: Mapping[str, str],
    strict_core: bool = True,
    require_physical_windows: bool = False,
    require_battery_present: bool = False,
) -> Tuple[bool, List[str], List[str], Dict[str, ValidationResult]]:
    observed: List[str] = []
    missing: List[str] = []
    results: Dict[str, ValidationResult] = {}
    for raw_platform in required_platforms:
        platform_name = normalize_platform_name(raw_platform)
        path = expected_evidence_path(root, platform_name)
        if not path.exists():
            missing.append(platform_name)
            continue
        observed.append(platform_name)
        expected_class = expected_class_by_platform.get(platform_name)
        results[platform_name] = validate_telemetry_file(
            path,
            expected_platform=platform_name,
            expected_evidence_class=expected_class,
            strict_core=strict_core,
            require_physical_windows=(require_physical_windows and platform_name == "windows"),
            require_battery_present=(require_battery_present and platform_name == "windows"),
        )
    ok = not missing and all(r.ok for r in results.values())
    return ok, sorted(set(observed)), sorted(set(missing)), results
