from __future__ import annotations

import dataclasses
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal

from butler_pc_core.company_policy.contracts import require_digest, sha256_text, stable_json_digest


SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
VAULT_REF_RE = re.compile(r"^local-vault://[A-Za-z0-9_.:/-]+$")
STATUS_VALUES = {"CANDIDATE", "ACTIVE", "DEPRECATED"}


class CompanyFactContractError(ValueError):
    pass


@dataclass(frozen=True)
class CompanyFactVaultRecord:
    schema_version: Literal["company_fact.vault_record.v1"]
    fact_id: str
    status: Literal["CANDIDATE", "ACTIVE", "DEPRECATED"]
    category: str
    question_patterns: list[str]
    keywords_required: list[str]
    keywords_any: list[str]
    answer_runtime_text: str
    source: str
    source_url: str | None
    source_doc: str | None
    verified_at: str
    expires_at: str | None
    confidence: float
    approved_by_digest: str | None
    approved_at: str | None
    previous_fact_digest: str | None
    fact_digest: str
    raw_text_logged: Literal[False]
    external_send_zero: Literal[True]

    def to_vault_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_vault_record_dict(data)
        return data


CompanyFact = CompanyFactVaultRecord
CandidateFact = CompanyFactVaultRecord


@dataclass(frozen=True)
class CompanyFactIndexEntry:
    schema_version: Literal["company_fact.index_entry.v1"]
    fact_id: str
    status: Literal["CANDIDATE", "ACTIVE", "DEPRECATED"]
    fact_ref: str
    fact_digest: str
    field_digests: dict[str, list[str] | str | None]
    display_hints: dict[str, str]
    confidence: float
    raw_text_logged: Literal[False]
    external_send_zero: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_index_entry_dict(data)
        return data


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso() -> str:
    return date.today().isoformat()


def _clean_text_list(values: Any, field_name: str, *, min_items: int = 0) -> list[str]:
    if not isinstance(values, list):
        raise CompanyFactContractError(f"{field_name}_NOT_LIST")
    cleaned = [str(item).strip() for item in values if str(item or "").strip()]
    if len(cleaned) < min_items:
        raise CompanyFactContractError(f"{field_name}_TOO_SHORT")
    return cleaned


def _require_unique(values: list[str], field_name: str) -> None:
    if len(set(values)) != len(values):
        raise CompanyFactContractError(f"{field_name}_DUPLICATE")


def _normalize_iso_date(value: Any, field_name: str, *, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise CompanyFactContractError(f"{field_name}_REQUIRED")
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except Exception as exc:
        raise CompanyFactContractError(f"{field_name}_DATE_INVALID") from exc


def _require_nonempty(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise CompanyFactContractError(f"{field_name}_REQUIRED")
    return text


def _assert_bool_flags(data: dict[str, Any], prefix: str) -> None:
    if data.get("raw_text_logged") is not False:
        raise CompanyFactContractError(f"{prefix}_RAW_TEXT_LOGGED_MUST_BE_FALSE")
    if data.get("external_send_zero") is not True:
        raise CompanyFactContractError(f"{prefix}_EXTERNAL_SEND_ZERO_REQUIRED")


def _unsigned_vault_dict(data: dict[str, Any]) -> dict[str, Any]:
    unsigned = dict(data)
    unsigned.pop("fact_digest", None)
    return unsigned


def compute_fact_digest(data: dict[str, Any]) -> str:
    return stable_json_digest(_unsigned_vault_dict(data))


def _field_digests(record: CompanyFactVaultRecord) -> dict[str, list[str] | str | None]:
    return {
        "question_patterns": [sha256_text(value) for value in record.question_patterns],
        "keywords_required": [sha256_text(value) for value in record.keywords_required],
        "keywords_any": [sha256_text(value) for value in record.keywords_any],
        "answer": sha256_text(record.answer_runtime_text),
        "source": sha256_text(record.source),
        "source_url": sha256_text(record.source_url) if record.source_url else None,
        "source_doc": sha256_text(record.source_doc) if record.source_doc else None,
    }


def _display_hints(record: CompanyFactVaultRecord) -> dict[str, str]:
    answer_digest = sha256_text(record.answer_runtime_text)
    source_digest = sha256_text(record.source)
    return {
        "answer_hint": f"digest:{answer_digest[7:15]}…",
        "source_hint": f"digest:{source_digest[7:15]}…",
    }


def make_company_fact_record(
    *,
    status: str,
    category: str,
    question_patterns: list[str],
    keywords_required: list[str] | None,
    keywords_any: list[str] | None,
    answer_runtime_text: str,
    source: str,
    source_url: str | None = None,
    source_doc: str | None = None,
    verified_at: str | None = None,
    expires_at: str | None = None,
    confidence: float,
    approved_by_digest: str | None = None,
    approved_at: str | None = None,
    previous_fact_digest: str | None = None,
    fact_id: str | None = None,
) -> CompanyFactVaultRecord:
    if status not in STATUS_VALUES:
        raise CompanyFactContractError("COMPANY_FACT_STATUS_INVALID")
    patterns = _clean_text_list(question_patterns, "QUESTION_PATTERNS", min_items=2)
    _require_unique(patterns, "QUESTION_PATTERNS")
    required = _clean_text_list(keywords_required or [], "KEYWORDS_REQUIRED")
    any_values = _clean_text_list(keywords_any or [], "KEYWORDS_ANY")
    answer = _require_nonempty(answer_runtime_text, "ANSWER")
    if len(answer) < 10:
        raise CompanyFactContractError("ANSWER_TOO_SHORT")
    source_value = _require_nonempty(source, "SOURCE")
    if confidence < 0 or confidence > 1:
        raise CompanyFactContractError("COMPANY_FACT_CONFIDENCE_INVALID")
    if status == "CANDIDATE" and confidence >= 1.0:
        raise CompanyFactContractError("CANDIDATE_CONFIDENCE_MUST_BE_BELOW_ONE")
    if status == "ACTIVE":
        if confidence != 1.0:
            raise CompanyFactContractError("ACTIVE_CONFIDENCE_MUST_BE_ONE")
        if not approved_by_digest or not approved_at:
            raise CompanyFactContractError("ACTIVE_APPROVAL_REQUIRED")
        require_digest(approved_by_digest, "approved_by")

    if approved_by_digest is not None:
        require_digest(approved_by_digest, "approved_by")
    if previous_fact_digest is not None:
        require_digest(previous_fact_digest, "previous_fact")

    data = {
        "schema_version": "company_fact.vault_record.v1",
        "fact_id": fact_id or "company-fact-" + uuid.uuid4().hex,
        "status": status,
        "category": _require_nonempty(category, "CATEGORY"),
        "question_patterns": patterns,
        "keywords_required": required,
        "keywords_any": any_values,
        "answer_runtime_text": answer,
        "source": source_value,
        "source_url": str(source_url).strip() if source_url else None,
        "source_doc": str(source_doc).strip() if source_doc else None,
        "verified_at": _normalize_iso_date(verified_at or today_iso(), "VERIFIED_AT", required=True),
        "expires_at": _normalize_iso_date(expires_at, "EXPIRES_AT"),
        "confidence": float(confidence),
        "approved_by_digest": approved_by_digest,
        "approved_at": approved_at,
        "previous_fact_digest": previous_fact_digest,
        "raw_text_logged": False,
        "external_send_zero": True,
    }
    data["fact_digest"] = compute_fact_digest(data)
    record = CompanyFactVaultRecord(**data)  # type: ignore[arg-type]
    validate_vault_record_dict(record.to_vault_dict())
    return record


def make_index_entry(*, record: CompanyFactVaultRecord, fact_ref: str) -> CompanyFactIndexEntry:
    entry = CompanyFactIndexEntry(
        schema_version="company_fact.index_entry.v1",
        fact_id=record.fact_id,
        status=record.status,
        fact_ref=fact_ref,
        fact_digest=record.fact_digest,
        field_digests=_field_digests(record),
        display_hints=_display_hints(record),
        confidence=record.confidence,
        raw_text_logged=False,
        external_send_zero=True,
    )
    validate_index_entry_dict(entry.to_dict())
    return entry


def validate_vault_record_dict(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "fact_id", "status", "category", "question_patterns",
        "keywords_required", "keywords_any", "answer_runtime_text", "source",
        "source_url", "source_doc", "verified_at", "expires_at", "confidence",
        "approved_by_digest", "approved_at", "previous_fact_digest", "fact_digest",
        "raw_text_logged", "external_send_zero",
    }
    if not isinstance(data, dict):
        raise CompanyFactContractError("COMPANY_FACT_NOT_OBJECT")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise CompanyFactContractError(f"COMPANY_FACT_UNKNOWN_FIELD_{unknown[0]}")
    if data.get("schema_version") != "company_fact.vault_record.v1":
        raise CompanyFactContractError("COMPANY_FACT_SCHEMA_INVALID")
    if data.get("status") not in STATUS_VALUES:
        raise CompanyFactContractError("COMPANY_FACT_STATUS_INVALID")
    _require_nonempty(data.get("fact_id"), "FACT_ID")
    _require_nonempty(data.get("category"), "CATEGORY")
    patterns = _clean_text_list(data.get("question_patterns"), "QUESTION_PATTERNS", min_items=2)
    _require_unique(patterns, "QUESTION_PATTERNS")
    _clean_text_list(data.get("keywords_required"), "KEYWORDS_REQUIRED")
    _clean_text_list(data.get("keywords_any"), "KEYWORDS_ANY")
    _require_nonempty(data.get("answer_runtime_text"), "ANSWER")
    _require_nonempty(data.get("source"), "SOURCE")
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        raise CompanyFactContractError("COMPANY_FACT_CONFIDENCE_INVALID")
    if data["status"] == "CANDIDATE" and confidence >= 1.0:
        raise CompanyFactContractError("CANDIDATE_CONFIDENCE_MUST_BE_BELOW_ONE")
    if data["status"] == "ACTIVE":
        if confidence != 1.0:
            raise CompanyFactContractError("ACTIVE_CONFIDENCE_MUST_BE_ONE")
        if not data.get("approved_by_digest") or not data.get("approved_at"):
            raise CompanyFactContractError("ACTIVE_APPROVAL_REQUIRED")
    if data.get("approved_by_digest") is not None:
        require_digest(data["approved_by_digest"], "approved_by")
    if data.get("previous_fact_digest") is not None:
        require_digest(data["previous_fact_digest"], "previous_fact")
    _normalize_iso_date(data.get("verified_at"), "VERIFIED_AT", required=True)
    _normalize_iso_date(data.get("expires_at"), "EXPIRES_AT")
    require_digest(data.get("fact_digest"), "fact")
    _assert_bool_flags(data, "COMPANY_FACT")
    if data["fact_digest"] != compute_fact_digest(data):
        raise CompanyFactContractError("COMPANY_FACT_DIGEST_MISMATCH")
    return data


def validate_index_entry_dict(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "fact_id", "status", "fact_ref", "fact_digest",
        "field_digests", "display_hints", "confidence", "raw_text_logged",
        "external_send_zero",
    }
    if not isinstance(data, dict):
        raise CompanyFactContractError("COMPANY_FACT_INDEX_NOT_OBJECT")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise CompanyFactContractError(f"COMPANY_FACT_INDEX_UNKNOWN_FIELD_{unknown[0]}")
    if data.get("schema_version") != "company_fact.index_entry.v1":
        raise CompanyFactContractError("COMPANY_FACT_INDEX_SCHEMA_INVALID")
    if data.get("status") not in STATUS_VALUES:
        raise CompanyFactContractError("COMPANY_FACT_INDEX_STATUS_INVALID")
    _require_nonempty(data.get("fact_id"), "FACT_ID")
    if not isinstance(data.get("fact_ref"), str) or not VAULT_REF_RE.match(data["fact_ref"]):
        raise CompanyFactContractError("COMPANY_FACT_REF_INVALID")
    require_digest(data.get("fact_digest"), "fact")
    if not isinstance(data.get("field_digests"), dict):
        raise CompanyFactContractError("COMPANY_FACT_FIELD_DIGESTS_INVALID")
    if not isinstance(data.get("display_hints"), dict):
        raise CompanyFactContractError("COMPANY_FACT_DISPLAY_HINTS_INVALID")
    if not isinstance(data.get("confidence"), (int, float)):
        raise CompanyFactContractError("COMPANY_FACT_INDEX_CONFIDENCE_INVALID")
    _assert_bool_flags(data, "COMPANY_FACT_INDEX")
    return data
