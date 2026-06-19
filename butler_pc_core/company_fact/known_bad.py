from __future__ import annotations

import dataclasses
import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from butler_pc_core.company_policy.contracts import require_digest, sha256_text, stable_json_digest
from butler_pc_core.factpack.matcher import Matcher
from butler_pc_core.factpack.schema import Fact, FactMatch


DEPRECATE_REASON_CODES = {"WRONG", "SUPERSEDED", "MANUAL_DEPRECATED"}
KNOWN_BAD_REASON_CODES = {"WRONG"}
KNOWN_BAD_THRESHOLD = Matcher.DEFAULT_THRESHOLD
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class KnownBadContractError(ValueError):
    pass


@dataclass(frozen=True)
class KnownBadVaultEntry:
    """Encrypted runtime entry used only to build the matcher.

    question_patterns and keywords are intentionally vault-only. The persisted
    known-bad index stores only digests, status and counters so audit/index logs
    remain raw-zero while runtime matching still reuses FactPack's conservative
    keyword + pattern matcher.
    """

    schema_version: Literal["company_fact.known_bad_vault_entry.v1"]
    bad_entry_id: str
    bad_fact_id: str
    bad_fact_digest: str
    category: str
    question_patterns: list[str]
    keywords_required: list[str]
    keywords_any: list[str]
    answer_digest: str
    source_digest: str
    source_url_digest: str | None
    source_doc_digest: str | None
    reason_code: Literal["WRONG"]
    status: Literal["ACTIVE", "DEPRECATED"]
    created_by_digest: str
    updated_by_digest: str
    created_at: str
    updated_at: str
    bad_entry_digest: str
    raw_text_logged: Literal[False]
    external_send_zero: Literal[True]

    def to_vault_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_known_bad_vault_entry(data)
        return data


@dataclass(frozen=True)
class KnownBadIndexEntry:
    schema_version: Literal["company_fact.known_bad_index_entry.v1"]
    bad_entry_id: str
    bad_fact_id: str
    bad_fact_digest: str
    known_bad_ref: str
    category_digest: str
    question_pattern_digests: list[str]
    keywords_required_digests: list[str]
    keywords_any_digests: list[str]
    answer_digest: str
    source_digest: str
    source_url_digest: str | None
    source_doc_digest: str | None
    reason_code: Literal["WRONG"]
    status: Literal["ACTIVE", "DEPRECATED"]
    created_by_digest: str
    updated_by_digest: str
    bad_entry_digest: str
    raw_text_logged: Literal[False]
    external_send_zero: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_known_bad_index_entry(data)
        return data


@dataclass(frozen=True)
class KnownBadOverrideRecord:
    schema_version: Literal["company_fact.known_bad_override.v1"]
    fact_id: str
    candidate_fact_digest: str
    bad_entry_id: str
    bad_fact_digest: str
    approved_by_digest: str
    approved_at: str
    status: Literal["ACTIVE", "REVOKED"]
    override_digest: str
    raw_text_logged: Literal[False]
    external_send_zero: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_known_bad_override_record(data)
        return data


@dataclass(frozen=True)
class KnownBadMatch:
    bad_entry_id: str
    bad_fact_digest: str
    score: float
    matched_pattern_digest: str
    matched_keywords_count: int
    raw_text_logged: Literal[False] = False
    external_send_zero: Literal[True] = True

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _require_digest(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.match(value):
        raise KnownBadContractError(f"{field}_DIGEST_INVALID")
    return value


def _clean_list(values: Any, field: str, *, min_items: int = 0) -> list[str]:
    if not isinstance(values, list):
        raise KnownBadContractError(f"{field}_NOT_LIST")
    out = [str(v).strip() for v in values if str(v or '').strip()]
    if len(out) < min_items:
        raise KnownBadContractError(f"{field}_TOO_SHORT")
    if len(set(out)) != len(out):
        raise KnownBadContractError(f"{field}_DUPLICATE")
    return out


def compute_known_bad_digest(data: dict[str, Any]) -> str:
    unsigned = dict(data)
    unsigned.pop('bad_entry_digest', None)
    return stable_json_digest(unsigned)


def compute_known_bad_override_digest(data: dict[str, Any]) -> str:
    unsigned = dict(data)
    unsigned.pop("override_digest", None)
    return stable_json_digest(unsigned)


def build_known_bad_vault_entry(*, record: Any, actor_digest: str, created_at: str) -> KnownBadVaultEntry:
    require_digest(actor_digest, 'actor')
    data = {
        'schema_version': 'company_fact.known_bad_vault_entry.v1',
        'bad_entry_id': 'known-bad-' + uuid.uuid4().hex,
        'bad_fact_id': record.fact_id,
        'bad_fact_digest': record.fact_digest,
        'category': str(record.category),
        'question_patterns': list(record.question_patterns),
        'keywords_required': list(record.keywords_required),
        'keywords_any': list(record.keywords_any),
        'answer_digest': sha256_text(record.answer_runtime_text),
        'source_digest': sha256_text(record.source),
        'source_url_digest': sha256_text(record.source_url) if record.source_url else None,
        'source_doc_digest': sha256_text(record.source_doc) if record.source_doc else None,
        'reason_code': 'WRONG',
        'status': 'ACTIVE',
        'created_by_digest': actor_digest,
        'updated_by_digest': actor_digest,
        'created_at': created_at,
        'updated_at': created_at,
        'raw_text_logged': False,
        'external_send_zero': True,
    }
    data['bad_entry_digest'] = compute_known_bad_digest(data)
    entry = KnownBadVaultEntry(**data)  # type: ignore[arg-type]
    validate_known_bad_vault_entry(entry.to_vault_dict())
    return entry


def make_known_bad_override_record(
    *,
    fact_id: str,
    candidate_fact_digest: str,
    bad_entry_id: str,
    bad_fact_digest: str,
    approved_by_digest: str,
    approved_at: str,
) -> KnownBadOverrideRecord:
    require_digest(candidate_fact_digest, "candidate_fact")
    require_digest(bad_fact_digest, "bad_fact")
    require_digest(approved_by_digest, "approved_by")
    data = {
        "schema_version": "company_fact.known_bad_override.v1",
        "fact_id": str(fact_id or "").strip(),
        "candidate_fact_digest": candidate_fact_digest,
        "bad_entry_id": str(bad_entry_id or "").strip(),
        "bad_fact_digest": bad_fact_digest,
        "approved_by_digest": approved_by_digest,
        "approved_at": str(approved_at or "").strip(),
        "status": "ACTIVE",
        "raw_text_logged": False,
        "external_send_zero": True,
    }
    data["override_digest"] = compute_known_bad_override_digest(data)
    record = KnownBadOverrideRecord(**data)  # type: ignore[arg-type]
    validate_known_bad_override_record(record.to_dict())
    return record


def make_known_bad_index_entry(*, entry: KnownBadVaultEntry, known_bad_ref: str) -> KnownBadIndexEntry:
    index = KnownBadIndexEntry(
        schema_version='company_fact.known_bad_index_entry.v1',
        bad_entry_id=entry.bad_entry_id,
        bad_fact_id=entry.bad_fact_id,
        bad_fact_digest=entry.bad_fact_digest,
        known_bad_ref=known_bad_ref,
        category_digest=sha256_text(entry.category),
        question_pattern_digests=[sha256_text(v) for v in entry.question_patterns],
        keywords_required_digests=[sha256_text(v) for v in entry.keywords_required],
        keywords_any_digests=[sha256_text(v) for v in entry.keywords_any],
        answer_digest=entry.answer_digest,
        source_digest=entry.source_digest,
        source_url_digest=entry.source_url_digest,
        source_doc_digest=entry.source_doc_digest,
        reason_code=entry.reason_code,
        status=entry.status,
        created_by_digest=entry.created_by_digest,
        updated_by_digest=entry.updated_by_digest,
        bad_entry_digest=entry.bad_entry_digest,
        raw_text_logged=False,
        external_send_zero=True,
    )
    validate_known_bad_index_entry(index.to_dict())
    return index


def _fact_from_known_bad(entry: KnownBadVaultEntry) -> Fact:
    verified = date.fromisoformat(entry.created_at[:10])
    return Fact(
        id=entry.bad_entry_id,
        category=entry.category,
        question_patterns=entry.question_patterns,
        keywords_required=entry.keywords_required,
        keywords_any=entry.keywords_any,
        answer='known-bad digest only',
        source='known-bad digest only',
        source_url=None,
        source_doc=None,
        verified_at=verified,
        expires_at=None,
        confidence=1.0,
    )


def match_known_bad_candidate(candidate: Any, entries: list[KnownBadVaultEntry], *, threshold: float = KNOWN_BAD_THRESHOLD) -> KnownBadMatch | None:
    active = [entry for entry in entries if entry.status == 'ACTIVE']
    if not active:
        return None
    matcher = Matcher([_fact_from_known_bad(entry) for entry in active], threshold=threshold)
    best: FactMatch | None = None
    for question in candidate.question_patterns:
        found = matcher.lookup(question)
        if found is None:
            continue
        if best is None or (found.score, found.fact.id) > (best.score, best.fact.id):
            best = found
    if best is None:
        return None
    matched_entry = next(entry for entry in active if entry.bad_entry_id == best.fact.id)
    return KnownBadMatch(
        bad_entry_id=matched_entry.bad_entry_id,
        bad_fact_digest=matched_entry.bad_fact_digest,
        score=round(float(best.score), 6),
        matched_pattern_digest=sha256_text(best.matched_pattern),
        matched_keywords_count=len(best.matched_keywords),
    )


def validate_known_bad_override_record(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "fact_id", "candidate_fact_digest", "bad_entry_id",
        "bad_fact_digest", "approved_by_digest", "approved_at", "status",
        "override_digest", "raw_text_logged", "external_send_zero",
    }
    if not isinstance(data, dict):
        raise KnownBadContractError("KNOWN_BAD_OVERRIDE_NOT_OBJECT")
    if set(data) - allowed:
        raise KnownBadContractError("KNOWN_BAD_OVERRIDE_UNKNOWN_FIELD")
    if data.get("schema_version") != "company_fact.known_bad_override.v1":
        raise KnownBadContractError("KNOWN_BAD_OVERRIDE_SCHEMA_INVALID")
    if not str(data.get("fact_id") or "").strip():
        raise KnownBadContractError("KNOWN_BAD_OVERRIDE_FACT_ID_REQUIRED")
    if not str(data.get("bad_entry_id") or "").strip():
        raise KnownBadContractError("KNOWN_BAD_OVERRIDE_BAD_ENTRY_REQUIRED")
    if not str(data.get("approved_at") or "").strip():
        raise KnownBadContractError("KNOWN_BAD_OVERRIDE_APPROVED_AT_REQUIRED")
    if data.get("status") not in {"ACTIVE", "REVOKED"}:
        raise KnownBadContractError("KNOWN_BAD_OVERRIDE_STATUS_INVALID")
    for field in ["candidate_fact_digest", "bad_fact_digest", "approved_by_digest", "override_digest"]:
        _require_digest(data.get(field), field)
    expected = compute_known_bad_override_digest(data)
    if expected != data.get("override_digest"):
        raise KnownBadContractError("KNOWN_BAD_OVERRIDE_DIGEST_MISMATCH")
    if data.get("raw_text_logged") is not False or data.get("external_send_zero") is not True:
        raise KnownBadContractError("KNOWN_BAD_OVERRIDE_FLAGS_INVALID")
    return data


def validate_known_bad_vault_entry(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        'schema_version', 'bad_entry_id', 'bad_fact_id', 'bad_fact_digest', 'category',
        'question_patterns', 'keywords_required', 'keywords_any', 'answer_digest', 'source_digest',
        'source_url_digest', 'source_doc_digest', 'reason_code', 'status', 'created_by_digest',
        'updated_by_digest', 'created_at', 'updated_at', 'bad_entry_digest', 'raw_text_logged',
        'external_send_zero',
    }
    if set(data) - allowed:
        raise KnownBadContractError('KNOWN_BAD_VAULT_UNKNOWN_FIELD')
    if data.get('schema_version') != 'company_fact.known_bad_vault_entry.v1':
        raise KnownBadContractError('KNOWN_BAD_VAULT_SCHEMA_INVALID')
    if data.get('reason_code') != 'WRONG':
        raise KnownBadContractError('KNOWN_BAD_REASON_INVALID')
    if data.get('status') not in {'ACTIVE', 'DEPRECATED'}:
        raise KnownBadContractError('KNOWN_BAD_STATUS_INVALID')
    _clean_list(data.get('question_patterns'), 'QUESTION_PATTERNS', min_items=2)
    _clean_list(data.get('keywords_required', []), 'KEYWORDS_REQUIRED')
    _clean_list(data.get('keywords_any', []), 'KEYWORDS_ANY')
    for field in ['bad_fact_digest', 'answer_digest', 'source_digest', 'created_by_digest', 'updated_by_digest', 'bad_entry_digest']:
        _require_digest(data.get(field), field)
    for field in ['source_url_digest', 'source_doc_digest']:
        if data.get(field) is not None:
            _require_digest(data.get(field), field)
    expected = compute_known_bad_digest(data)
    if expected != data.get('bad_entry_digest'):
        raise KnownBadContractError('KNOWN_BAD_DIGEST_MISMATCH')
    if data.get('raw_text_logged') is not False or data.get('external_send_zero') is not True:
        raise KnownBadContractError('KNOWN_BAD_FLAGS_INVALID')
    return data


def validate_known_bad_index_entry(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        'schema_version', 'bad_entry_id', 'bad_fact_id', 'bad_fact_digest', 'known_bad_ref',
        'category_digest', 'question_pattern_digests', 'keywords_required_digests',
        'keywords_any_digests', 'answer_digest', 'source_digest', 'source_url_digest',
        'source_doc_digest', 'reason_code', 'status', 'created_by_digest', 'updated_by_digest',
        'bad_entry_digest', 'raw_text_logged', 'external_send_zero',
    }
    if set(data) - allowed:
        raise KnownBadContractError('KNOWN_BAD_INDEX_UNKNOWN_FIELD')
    if data.get('schema_version') != 'company_fact.known_bad_index_entry.v1':
        raise KnownBadContractError('KNOWN_BAD_INDEX_SCHEMA_INVALID')
    for field in ['bad_fact_digest', 'category_digest', 'answer_digest', 'source_digest', 'created_by_digest', 'updated_by_digest', 'bad_entry_digest']:
        _require_digest(data.get(field), field)
    for list_field in ['question_pattern_digests', 'keywords_required_digests', 'keywords_any_digests']:
        values = data.get(list_field)
        if not isinstance(values, list):
            raise KnownBadContractError(f'{list_field}_NOT_LIST')
        for value in values:
            _require_digest(value, list_field)
    for field in ['source_url_digest', 'source_doc_digest']:
        if data.get(field) is not None:
            _require_digest(data.get(field), field)
    if data.get('reason_code') != 'WRONG':
        raise KnownBadContractError('KNOWN_BAD_INDEX_REASON_INVALID')
    if data.get('raw_text_logged') is not False or data.get('external_send_zero') is not True:
        raise KnownBadContractError('KNOWN_BAD_INDEX_FLAGS_INVALID')
    return data
