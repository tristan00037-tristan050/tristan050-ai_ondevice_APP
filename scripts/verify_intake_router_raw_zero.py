from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.connect_loop.attachment_features import RuntimeAttachment, extract_attachment_features
from butler_pc_core.connect_loop.intake_router import IntakeContractError, assert_intake_payload_safe, decide_intake


FORBIDDEN_KEYS = {
    "filename",
    "file_name",
    "file_path",
    "absolute_path",
    "raw_text",
    "source_text_runtime",
    "document_text",
    "cell_text",
    "sample_cell_value",
    "runtime_file_text",
}

FORBIDDEN_VALUES = {
    "/Users/private/path",
    "sk-proj-secret-like-token",
    "alice@example.com",
    "bank_secret.csv",
    "2026-01-01,1000,0,1000",
}


class RawZeroVerifierFailure(Exception):
    """Short-code failure used to keep verifier output raw-free."""


def _walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield ("key", str(key))
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
    elif isinstance(value, str):
        yield ("value", value)


def _assert_no_forbidden_surface(value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for kind, item in _walk(value):
        lowered = item.lower()
        if kind == "key" and lowered in FORBIDDEN_KEYS:
            raise RawZeroVerifierFailure("FORBIDDEN_KEY")
    for raw in FORBIDDEN_VALUES:
        if raw in encoded:
            raise RawZeroVerifierFailure("FORBIDDEN_VALUE")
    try:
        assert_intake_payload_safe(value)
    except IntakeContractError as exc:
        raise RawZeroVerifierFailure(exc.fail_class) from exc


def main() -> int:
    try:
        raw = (
            "거래일자,입금,출금,잔액,적요\n"
            "/Users/private/path,sk-proj-secret-like-token,alice@example.com,1000\n"
        ).encode("utf-8")
        bundle = extract_attachment_features([
            RuntimeAttachment(raw, filename="bank_secret.csv", content_type="text/csv")
        ])
        decisions = [
            decide_intake(
                request_id="raw-zero-policy-on",
                attachment_bundle=bundle,
                runtime_text="분개",
                policy_ready_override=True,
            ),
            decide_intake(
                request_id="raw-zero-policy-off",
                attachment_bundle=bundle,
                runtime_text="분개",
                policy_ready_override=False,
            ),
        ]
        for decision in decisions:
            _assert_no_forbidden_surface(decision)
    except RawZeroVerifierFailure as exc:
        print("RAW_FIELD_ZERO=0")
        print(f"ERROR_CODE={exc}", file=sys.stderr)
        return 1
    except Exception:
        print("RAW_FIELD_ZERO=0")
        print("ERROR_CODE=VERIFIER_INTERNAL_ERROR", file=sys.stderr)
        return 1
    print("RAW_FIELD_ZERO=1")
    print("INTAKE_ROUTER_RAW_ZERO_VERIFIER=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
