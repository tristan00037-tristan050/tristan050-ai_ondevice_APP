#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.company_fact.extractor import (  # noqa: E402
    EvidenceUnitRuntime,
    extract_company_fact_candidate,
    sha256_text,
)


FORBIDDEN_KEYS = {
    "candidate_draft",
    "answer_runtime_text",
    "source_text_runtime_only",
    "text_runtime_only",
    "raw_text",
    "document_text",
    "source_text",
    "file_path",
    "filename",
    "sample_cell_value",
}

FORBIDDEN_VALUES = {
    "출장비는 3만원 이하만 영수증으로 정산합니다.",
    "사내규정 원문",
    "/Users/private/company-policy.txt",
    "alice@example.com",
    "sk-proj-secret-like-token",
    "1234567890",
}


class VerifyFailure(Exception):
    pass


def _walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield "key", str(key)
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
    elif isinstance(value, str):
        yield "value", value


def _assert_raw_free(value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for kind, item in _walk(value):
        if kind == "key" and item in FORBIDDEN_KEYS:
            raise VerifyFailure("FORBIDDEN_KEY")
    for raw in FORBIDDEN_VALUES:
        if raw in encoded:
            raise VerifyFailure("FORBIDDEN_VALUE")


def main() -> int:
    try:
        text = (
            "Q: 출장비 정산 기준은?\n"
            "A: 출장비는 3만원 이하만 영수증으로 정산합니다.\n"
            "출처: 사내규정 원문\n"
            "시행일: 2026년 6월 16일\n"
        )
        outcome = extract_company_fact_candidate(
            {"primary_destination": "company_fact_candidate"},
            {"feature_set_digest": sha256_text("feature")},
            "회사 규정",
            evidence_units_runtime_only=[
                EvidenceUnitRuntime(
                    unit_id="u1",
                    text_runtime_only=text,
                    source_digest=sha256_text("source"),
                    unit_digest=sha256_text(text),
                    unit_kind="qa",
                    order=0,
                )
            ],
        )
        if outcome.status != "draft_ready":
            raise VerifyFailure("DRAFT_NOT_READY")
        _assert_raw_free(outcome.to_audit_dict())

        blocked = extract_company_fact_candidate(
            {},
            {},
            "회사 규정 alice@example.com",
            source_text_runtime_only="/Users/private/company-policy.txt sk-proj-secret-like-token 1234567890",
        )
        if blocked.status != "abstain" or blocked.reason_code != "DLP_OR_SECRET_BLOCKED":
            raise VerifyFailure("DLP_NOT_BLOCKED")
        _assert_raw_free(blocked.to_audit_dict())
    except VerifyFailure as exc:
        print("COMPANY_FACT_EXTRACTOR_RAW_ZERO=0")
        print(f"ERROR_CODE={exc}", file=sys.stderr)
        return 1
    except Exception:
        print("COMPANY_FACT_EXTRACTOR_RAW_ZERO=0")
        print("ERROR_CODE=VERIFIER_INTERNAL_ERROR", file=sys.stderr)
        return 1
    print("COMPANY_FACT_EXTRACTOR_RAW_ZERO=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
