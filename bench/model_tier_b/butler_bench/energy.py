from __future__ import annotations

import re
from typing import Any

from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_energy_receipt(receipt: dict[str, Any], *, energy_required: bool, run_start_ns: int, run_end_ns: int) -> str:
    base = {"schema_version", "status", "reason", "measurement_source", "source_binary_sha256", "unit", "interval_start_ns", "interval_end_ns", "energy_microjoules"}
    if set(receipt) != base or receipt["schema_version"] != "butler.model-tier-b.energy.v2.8":
        _block("ENERGY_KEYS")
    status = receipt["status"]
    if status == "NOT_MEASURED":
        if energy_required:
            _block("ENERGY_REQUIRED_NOT_MEASURED")
        if not isinstance(receipt["reason"], str) or not receipt["reason"]:
            _block("ENERGY_REASON")
        if any(receipt[key] is not None for key in ("measurement_source", "source_binary_sha256", "unit", "interval_start_ns", "interval_end_ns", "energy_microjoules")):
            _block("ENERGY_ESTIMATE_PRESENT")
        return "NOT_MEASURED"
    if status != "MEASURED":
        _block("ENERGY_STATUS")
    if receipt["reason"] is not None:
        _block("ENERGY_REASON_ON_MEASURED")
    if receipt["measurement_source"] not in {"APPROVED_HARDWARE_METER", "APPROVED_OS_ENERGY_COUNTER"}:
        _block("ENERGY_SOURCE")
    if not isinstance(receipt["source_binary_sha256"], str) or not _SHA256.fullmatch(receipt["source_binary_sha256"]):
        _block("ENERGY_SOURCE_DIGEST")
    if receipt["unit"] != "microjoule":
        _block("ENERGY_UNIT")
    if receipt["interval_start_ns"] != run_start_ns or receipt["interval_end_ns"] != run_end_ns:
        _block("ENERGY_INTERVAL")
    if type(receipt["energy_microjoules"]) is not int or receipt["energy_microjoules"] <= 0:
        _block("ENERGY_VALUE")
    return "MEASURED"


def reject_estimated_energy(power_watts: object, elapsed_seconds: object) -> None:
    if power_watts is not None or elapsed_seconds is not None:
        _block("ENERGY_ESTIMATED_WITHOUT_METER")


def _block(detail: str) -> None:
    raise GateError(FailClass.MEASUREMENT, detail, exit_code=ExitCode.ENVIRONMENT)
