from __future__ import annotations

import re
from typing import Any

from .canonical import canonical_sha256
from .errors import ExitCode, FailClass, GateError
from .preflight import GATE_NAMES

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def build_final_status(*, gate_receipts: dict[str, dict[str, Any]], status: str) -> dict[str, Any]:
    if set(gate_receipts) != set(GATE_NAMES):
        _block("FINAL_GATE_SET")
    gates: dict[str, dict[str, Any]] = {}
    for name in GATE_NAMES:
        receipt = gate_receipts[name]
        if not isinstance(receipt, dict) or set(receipt) != {"value", "receipt_sha256"}:
            _block("FINAL_GATE_ENTRY")
        if type(receipt["value"]) is not bool or not isinstance(receipt["receipt_sha256"], str) or not _SHA256.fullmatch(receipt["receipt_sha256"]):
            _block("FINAL_GATE_VALUE")
        gates[name] = receipt
    all_true = all(item["value"] for item in gates.values())
    allowed = {"BLOCKED", "SPEC_READY", "CODE_READY_FOR_AUDIT", "READY_FOR_OWNER_M3_RUN", "M3_EVIDENCE_VALID_M4_PENDING"}
    if status not in allowed:
        _block("G1_STATUS_FORBIDDEN")
    if status in {"READY_FOR_OWNER_M3_RUN", "M3_EVIDENCE_VALID_M4_PENDING"} and not all_true:
        _block("PREMATURE_STATUS")
    payload = {
        "schema_version": "butler.model-tier-b.final-status.v2.8",
        "status": status,
        "gates": gates,
    }
    payload["subject_sha256"] = canonical_sha256(payload)
    return payload


def validate_defect_closure_receipts(receipts: list[dict[str, Any]], expected_defect_ids: set[str]) -> str:
    if len(receipts) != len(expected_defect_ids) or len(expected_defect_ids) != 46:
        _block("DEFECT_CLOSURE_CARDINALITY")
    observed: set[str] = set()
    digests: list[str] = []
    for receipt in receipts:
        if not isinstance(receipt, dict) or set(receipt) != {"defect_id", "code_sha256", "test_sha256", "ci_receipt_sha256", "independent_replay_sha256", "closed"}:
            _block("DEFECT_CLOSURE_KEYS")
        defect_id = receipt["defect_id"]
        if defect_id not in expected_defect_ids or defect_id in observed or receipt["closed"] is not True:
            _block("DEFECT_CLOSURE_ID_OR_VALUE")
        for key in ("code_sha256", "test_sha256", "ci_receipt_sha256", "independent_replay_sha256"):
            if not isinstance(receipt[key], str) or not _SHA256.fullmatch(receipt[key]):
                _block("DEFECT_CLOSURE_DIGEST")
        observed.add(defect_id)
        digests.append(canonical_sha256(receipt))
    return canonical_sha256(sorted(digests))


def _block(detail: str) -> None:
    raise GateError(FailClass.PREFLIGHT, detail, exit_code=ExitCode.PROTOCOL)
