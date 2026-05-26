from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

REQUIRED_FIELDS = ["제목", "발행일", "담당자", "핵심 내용", "합의사항", "금액/일정", "확인 필요", "최종 문안"]
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RAW_FORBIDDEN_KEYS = {"foreign_doc", "our_format", "reference_text", "expected_output", "raw_text", "source_text"}


@dataclass(frozen=True)
class EvalSetReport:
    schema_version: str
    eval_set_path: str
    sample_count: int
    digest_only: bool
    raw_text_included: bool
    required_fields_ok: bool
    mock_result: bool
    contract_only: bool
    status: str
    invalid_case_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def iter_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc


def inspect_eval_set(path: str | Path) -> EvalSetReport:
    rows = list(iter_jsonl(path))
    invalid: list[str] = []
    raw_text_included = False
    required_fields_ok = True
    digest_only = True

    for index, row in enumerate(rows, start=1):
        case_id = str(row.get("case_id", f"line_{index}"))
        if RAW_FORBIDDEN_KEYS.intersection(row.keys()):
            raw_text_included = True
            invalid.append(case_id + ":raw_key")
        if row.get("required_fields") != REQUIRED_FIELDS:
            required_fields_ok = False
            invalid.append(case_id + ":required_fields")
        for key in ("foreign_doc_digest", "our_format_digest", "semantic_checklist_digest", "format_marker_digest"):
            if not isinstance(row.get(key), str) or not DIGEST_RE.match(row[key]):
                digest_only = False
                invalid.append(case_id + f":{key}")

    status = "PASS_V2_EVAL_SET_CONTRACT" if len(rows) >= 20 and digest_only and not raw_text_included and required_fields_ok else "BLOCK_V2_EVAL_SET_CONTRACT"
    return EvalSetReport(
        schema_version="box2.helper3.eval_set_report.v2",
        eval_set_path=str(path),
        sample_count=len(rows),
        digest_only=digest_only,
        raw_text_included=raw_text_included,
        required_fields_ok=required_fields_ok,
        mock_result=False,
        contract_only=True,
        status=status,
        invalid_case_ids=invalid,
    )
