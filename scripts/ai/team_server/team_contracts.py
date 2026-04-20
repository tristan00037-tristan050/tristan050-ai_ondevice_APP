from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Dict, List, Mapping, Tuple
import json
import re


RAW_FIELD_NAMES = {
    "raw",
    "raw_text",
    "raw_content",
    "content",
    "body",
    "document",
    "document_text",
    "audio",
    "audio_text",
    "audio_blob",
    "transcript",
    "prompt",
    "output",
    "input",
    "message",
    "source_text",
}

SENSITIVE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)token\s*[:=]\s*[A-Za-z0-9_\-]{8,}"),
    re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|PRIVATE) KEY-----"),
]


class AccessLevel(str, Enum):
    PUBLIC = "PUBLIC"
    TEAM = "TEAM"
    DEPT = "DEPT"
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"


class EventType(str, Enum):
    COLLECT = "COLLECT"
    RAG_QUERY = "RAG_QUERY"
    FINETUNE_TRIGGER = "FINETUNE_TRIGGER"
    POLICY_BLOCK = "POLICY_BLOCK"
    AUDIT = "AUDIT"


class ServerStatus(str, Enum):
    NORMAL = "NORMAL"
    SAFE_MODE = "SAFE_MODE"
    DEGRADED = "DEGRADED"


ACCESS_ORDER = {
    AccessLevel.PUBLIC: 0,
    AccessLevel.TEAM: 1,
    AccessLevel.DEPT: 2,
    AccessLevel.RESTRICTED: 3,
    AccessLevel.CONFIDENTIAL: 4,
}


@dataclass(frozen=True)
class DeviceMeta:
    device_id: str
    team_id: str
    session_id: str
    task: str
    input_digest16: str
    output_digest16: str
    selected_model: str
    timestamp: str


@dataclass(frozen=True)
class KBDocument:
    doc_id: str
    title_digest16: str
    summary: str
    tags: List[str]
    version: int
    lineage_id: str
    access_level: AccessLevel
    created_at: str
    team_id: str = "default"
    source_ref: str = ""


@dataclass(frozen=True)
class RAGRequest:
    query_digest16: str
    team_id: str
    user_id: str
    policy_id: str
    top_k: int


@dataclass(frozen=True)
class RAGResponse:
    hit_count: int
    results_meta: List[Dict[str, Any]]
    access_denied_count: int
    query_digest16: str


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str
    policy_id: str
    blocked_fields: List[str]


@dataclass(frozen=True)
class FinetuneJob:
    job_id: str
    team_id: str
    trigger_reason: str
    data_count: int
    created_at: str
    status: str
    model_version: str


@dataclass(frozen=True)
class TeamServerResponse:
    ok: bool
    event_type: str
    team_id: str
    result_digest16: str
    policy_code: str
    error_code: str


@dataclass(frozen=True)
class CollectResult:
    accepted: bool
    team_id: str
    stored_doc_id: str
    counter: int
    trigger_job_id: str | None
    reason_code: str = ""


@dataclass(frozen=True)
class IndexResult:
    accepted: bool
    doc_id: str
    team_id: str
    reason_code: str = ""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest16(value: Any) -> str:
    if is_dataclass(value):
        payload = json.dumps(asdict(value), sort_keys=True, default=str)
    elif isinstance(value, (dict, list, tuple)):
        payload = json.dumps(value, sort_keys=True, default=str)
    else:
        payload = str(value)
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def ensure_digest16(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{16}", value or ""))


def contains_sensitive_text(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)


def _looks_like_raw_string(value: str) -> bool:
    stripped = value.strip()
    if len(stripped) < 80:
        return False
    if "\n" in stripped:
        return True
    return len(stripped.split()) >= 15


def scan_for_raw_payload(payload: Any) -> Tuple[bool, str]:
    if is_dataclass(payload):
        payload = asdict(payload)
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_l = str(key).lower()
            if key_l in RAW_FIELD_NAMES:
                return True, f"raw_field:{key}"
            found, reason = scan_for_raw_payload(value)
            if found:
                return True, reason
        return False, ""
    if isinstance(payload, (list, tuple, set)):
        for item in payload:
            found, reason = scan_for_raw_payload(item)
            if found:
                return True, reason
        return False, ""
    if isinstance(payload, str) and _looks_like_raw_string(payload):
        return True, "raw_like_string"
    return False, ""


def safe_jsonable(value: Any) -> Dict[str, Any] | List[Any] | str | int | float | bool | None:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): safe_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_jsonable(v) for v in value]
    return value
