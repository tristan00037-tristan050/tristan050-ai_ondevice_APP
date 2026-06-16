from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Sequence

from butler_pc_core.company_fact.routes import CompanyFactCandidateRequest


SCHEMA_VERSION = "company_fact.extraction_outcome.v1"
MAX_EVIDENCE_UNITS = 50
MAX_EVIDENCE_UNIT_CHARS = 4000
MAX_EVIDENCE_TOTAL_CHARS = 64000

_SHA_PREFIX = "sha256:"
_CATEGORY_VALUES = {
    "company_policy",
    "hr_policy",
    "accounting_policy",
    "security_policy",
    "company_profile",
    "general_company_fact",
}
_SOURCE_LABELS = {"출처", "source", "문서", "문서명", "source_doc", "근거문서"}
_DATE_LABELS = {"시행일", "verified_at", "검증일", "등록일", "날짜"}
_QUESTION_LABELS = {"q", "질문", "question"}
_ANSWER_LABELS = {"a", "답변", "answer"}

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_LOCAL_PATH_RE = re.compile(r"(/Users/|/home/|/Volumes/|[A-Za-z]:\\|file://)", re.I)
_SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9_-]{10,}|pk-[a-z0-9_-]{10,}|AKIA[0-9A-Z]{12,}|"
    r"bearer\s+[a-z0-9._~+/=-]{10,}|api[_-]?key\s*[:=]\s*\S+|"
    r"password\s*[:=]\s*\S+|secret\s*[:=]\s*\S+)"
)
_HIGH_ENTROPY_RE = re.compile(r"\b(?:[A-Fa-f0-9]{32,}|[A-Za-z0-9+/]{40,}={0,2})\b")
_ACCOUNT_LIKE_RE = re.compile(r"\b(?:\d[\s-]?){10,}\b")
_LABEL_RE = re.compile(r"^\s*([^:：]{1,40})\s*[:：]\s*(.+?)\s*$")
_QA_RE = re.compile(r"^\s*(Q|질문|question|A|답변|answer)\s*[:：]\s*(.+?)\s*$", re.I)
_DATE_PATTERNS = (
    re.compile(r"(?P<y>\d{4})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})"),
    re.compile(r"(?P<y>\d{4})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일"),
)


def sha256_text(text: str) -> str:
    return _SHA_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(encoded)


@dataclass(frozen=True)
class EvidenceUnitRuntime:
    unit_id: str
    text_runtime_only: str
    source_digest: str
    unit_digest: str
    unit_kind: Literal["qa", "label_value", "paragraph", "table_header_value"] = "paragraph"
    order: int = 0
    raw_text_logged: Literal[False] = False
    external_send_zero: Literal[True] = True


@dataclass(frozen=True)
class ExtractionOutcome:
    schema_version: Literal["company_fact.extraction_outcome.v1"]
    status: Literal["draft_ready", "needs_confirmation", "abstain"]
    candidate_draft: dict[str, Any] | None
    missing_fields: list[str] = field(default_factory=list)
    reason_code: str = ""
    confidence: float = 0.0
    evidence_digests: list[str] = field(default_factory=list)
    source_digest: str | None = None
    draft_digest: str | None = None
    raw_text_logged: Literal[False] = False
    external_send_zero: Literal[True] = True
    auto_submit_zero: Literal[True] = True
    approve_called_zero: Literal[True] = True

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "missing_fields": list(self.missing_fields),
            "reason_code": self.reason_code,
            "confidence": self.confidence,
            "evidence_digests": list(self.evidence_digests),
            "source_digest": self.source_digest,
            "draft_digest": self.draft_digest,
            "raw_text_logged": False,
            "external_send_zero": True,
            "auto_submit_zero": True,
            "approve_called_zero": True,
        }


def _outcome(
    *,
    status: Literal["draft_ready", "needs_confirmation", "abstain"],
    reason_code: str,
    evidence_digests: Sequence[str],
    source_digest: str | None,
    candidate_draft: dict[str, Any] | None = None,
    missing_fields: Sequence[str] = (),
    confidence: float = 0.0,
) -> ExtractionOutcome:
    draft_digest = stable_json_digest(candidate_draft) if candidate_draft is not None else None
    return ExtractionOutcome(
        schema_version=SCHEMA_VERSION,
        status=status,
        candidate_draft=candidate_draft,
        missing_fields=list(missing_fields),
        reason_code=reason_code,
        confidence=round(float(confidence), 4),
        evidence_digests=list(evidence_digests),
        source_digest=source_digest,
        draft_digest=draft_digest,
    )


def _normalize_space(text: str) -> str:
    return " ".join(str(text or "").split())


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").casefold())


def _dlp_blocked(text: str) -> bool:
    if not text:
        return False
    if _EMAIL_RE.search(text) or _LOCAL_PATH_RE.search(text) or _SECRET_RE.search(text):
        return True
    if _HIGH_ENTROPY_RE.search(text) or _ACCOUNT_LIKE_RE.search(text):
        return True
    return False


def _safe_variant(question: str) -> str:
    base = re.sub(r"[?？!.。]+$", "", _normalize_space(question))
    if not base:
        return "회사 규정 알려줘"
    if base.endswith("알려줘"):
        return f"{base} 확인"
    return f"{base} 알려줘"


def _label_question(label: str) -> list[str]:
    clean = _normalize_space(label)
    return [f"{clean}은?", f"{clean} 알려줘"]


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [_normalize_space(part) for part in parts if _normalize_space(part)]


def _parse_iso_date(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            return date(int(match.group("y")), int(match.group("m")), int(match.group("d"))).isoformat()
        except ValueError:
            return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _infer_category(text: str) -> str:
    lowered = text.casefold()
    if any(term in lowered for term in ("회계", "정산", "경비", "세금", "증빙")):
        return "accounting_policy"
    if any(term in lowered for term in ("휴가", "연차", "근태", "인사", "채용")):
        return "hr_policy"
    if any(term in lowered for term in ("보안", "비밀번호", "권한", "접근", "개인정보")):
        return "security_policy"
    if any(term in lowered for term in ("회사명", "상호", "사업자", "대표자", "계좌")):
        return "company_profile"
    if any(term in lowered for term in ("규정", "정책", "내규", "기준")):
        return "company_policy"
    return "general_company_fact"


def _coerce_evidence_unit(value: Any, index: int, source_digest: str) -> EvidenceUnitRuntime:
    if isinstance(value, EvidenceUnitRuntime):
        return value
    if isinstance(value, str):
        text = value
        return EvidenceUnitRuntime(
            unit_id=f"unit-{index + 1}",
            text_runtime_only=text,
            source_digest=source_digest,
            unit_digest=sha256_text(text),
            unit_kind="paragraph",
            order=index,
        )
    if isinstance(value, dict):
        text = str(value.get("text_runtime_only") or "")
        return EvidenceUnitRuntime(
            unit_id=str(value.get("unit_id") or f"unit-{index + 1}"),
            text_runtime_only=text,
            source_digest=str(value.get("source_digest") or source_digest),
            unit_digest=str(value.get("unit_digest") or sha256_text(text)),
            unit_kind=value.get("unit_kind") if value.get("unit_kind") in {"qa", "label_value", "paragraph", "table_header_value"} else "paragraph",  # type: ignore[arg-type]
            order=int(value.get("order") or index),
        )
    text = str(value or "")
    return EvidenceUnitRuntime(
        unit_id=f"unit-{index + 1}",
        text_runtime_only=text,
        source_digest=source_digest,
        unit_digest=sha256_text(text),
        unit_kind="paragraph",
        order=index,
    )


def _prepare_evidence(
    source_text_runtime_only: str | None,
    evidence_units_runtime_only: Sequence[Any] | None,
) -> tuple[list[EvidenceUnitRuntime], str | None]:
    source_text = str(source_text_runtime_only or "")
    source_digest = sha256_text(source_text) if source_text else None
    if evidence_units_runtime_only is None:
        if not source_text:
            return [], source_digest
        return [
            EvidenceUnitRuntime(
                unit_id="source-text-1",
                text_runtime_only=source_text,
                source_digest=source_digest or sha256_text("empty-source"),
                unit_digest=sha256_text(source_text),
                unit_kind="paragraph",
                order=0,
            )
        ], source_digest
    units = [
        _coerce_evidence_unit(unit, idx, source_digest or sha256_text("runtime-evidence"))
        for idx, unit in enumerate(evidence_units_runtime_only)
    ]
    if source_digest is None and units:
        source_digest = units[0].source_digest
    return units, source_digest


def _evidence_limit_exceeded(units: Sequence[EvidenceUnitRuntime]) -> bool:
    if len(units) > MAX_EVIDENCE_UNITS:
        return True
    total = 0
    for unit in units:
        size = len(unit.text_runtime_only)
        if size > MAX_EVIDENCE_UNIT_CHARS:
            return True
        total += size
    return total > MAX_EVIDENCE_TOTAL_CHARS


def _label_map(text: str) -> dict[str, list[str]]:
    labels: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = _LABEL_RE.match(line)
        if not match:
            continue
        key = _normalize_space(match.group(1)).casefold()
        value = _normalize_space(match.group(2))
        labels.setdefault(key, []).append(value)
    return labels


def _first_label(labels: dict[str, list[str]], names: set[str]) -> str | None:
    for name in names:
        values = labels.get(name.casefold())
        if values:
            return values[0]
    return None


def _extract_qa(text: str) -> tuple[list[str], str | None]:
    questions: list[str] = []
    answers: list[str] = []
    for line in text.splitlines():
        match = _QA_RE.match(line)
        if not match:
            continue
        label = match.group(1).casefold()
        value = _normalize_space(match.group(2))
        if label in _QUESTION_LABELS and value:
            questions.append(value)
        elif label in _ANSWER_LABELS and value:
            answers.append(value)
    answer = answers[0] if answers else None
    return questions, answer


def _extract_label_value(labels: dict[str, list[str]]) -> tuple[str | None, str | None]:
    for raw_label, values in labels.items():
        label = _normalize_space(raw_label)
        if label.casefold() in _SOURCE_LABELS or label.casefold() in _DATE_LABELS:
            continue
        if label.casefold() in _QUESTION_LABELS or label.casefold() in _ANSWER_LABELS:
            continue
        if values:
            return label, values[0]
    return None, None


def _extract_paragraph_fact(text: str) -> tuple[list[str], str | None]:
    for sentence in _split_sentences(text):
        if any(term in sentence for term in ("없습니다", "없음", "없다", "일반 안내문", "구체 규정")):
            continue
        if len(sentence) >= 10 and any(term in sentence for term in ("규정", "정책", "기준", "절차")):
            topic = sentence.split("은", 1)[0] if "은" in sentence else sentence[:18]
            topic = _normalize_space(topic)
            return _label_question(topic), sentence
    return [], None


def _grounded(answer: str, evidence_text: str) -> bool:
    normalized_answer = _normalize_for_match(answer)
    normalized_evidence = _normalize_for_match(evidence_text)
    return bool(normalized_answer and normalized_answer in normalized_evidence)


def _validate_candidate_draft(candidate: dict[str, Any]) -> bool:
    try:
        CompanyFactCandidateRequest(**candidate)
        return True
    except Exception:
        return False


def _candidate_draft(
    *,
    questions: list[str],
    answer: str,
    source: str,
    labels: dict[str, list[str]],
    evidence_text: str,
    confidence: float,
) -> dict[str, Any]:
    unique_questions: list[str] = []
    for question in questions:
        cleaned = _normalize_space(question)
        if cleaned and cleaned not in unique_questions:
            unique_questions.append(cleaned)
    if len(unique_questions) == 1:
        variant = _safe_variant(unique_questions[0])
        if variant not in unique_questions:
            unique_questions.append(variant)
    category = _infer_category(" ".join([answer, source, evidence_text]))
    if category not in _CATEGORY_VALUES:
        category = "general_company_fact"
    verified_at = _parse_iso_date(_first_label(labels, _DATE_LABELS))
    return {
        "category": category,
        "question_patterns": unique_questions,
        "keywords_required": [],
        "keywords_any": [],
        "answer_runtime_text": _normalize_space(answer),
        "source": _normalize_space(source),
        "source_url": _first_label(labels, {"source_url", "url", "링크"}),
        "source_doc": _first_label(labels, {"문서명", "source_doc", "문서"}),
        "verified_at": verified_at,
        "expires_at": None,
        "confidence": round(float(confidence), 4),
    }


def extract_company_fact_candidate(
    intake_decision: dict[str, Any],
    attachment_features: dict[str, Any],
    runtime_text: str,
    *,
    source_text_runtime_only: str | None = None,
    evidence_units_runtime_only: Sequence[Any] | None = None,
) -> ExtractionOutcome:
    units, source_digest = _prepare_evidence(source_text_runtime_only, evidence_units_runtime_only)
    evidence_digests = [unit.unit_digest for unit in units]
    if not units:
        return _outcome(
            status="abstain",
            reason_code="NO_GROUNDING_TEXT",
            evidence_digests=evidence_digests,
            source_digest=source_digest,
        )
    if _evidence_limit_exceeded(units):
        return _outcome(
            status="abstain",
            reason_code="EVIDENCE_LIMIT_EXCEEDED",
            evidence_digests=evidence_digests,
            source_digest=source_digest,
        )
    evidence_text = "\n".join(unit.text_runtime_only for unit in sorted(units, key=lambda item: item.order))
    if _dlp_blocked("\n".join([str(runtime_text or ""), str(source_text_runtime_only or ""), evidence_text])):
        return _outcome(
            status="abstain",
            reason_code="DLP_OR_SECRET_BLOCKED",
            evidence_digests=evidence_digests,
            source_digest=source_digest,
        )

    labels = _label_map(evidence_text)
    source = _first_label(labels, _SOURCE_LABELS)
    questions, answer = _extract_qa(evidence_text)
    confidence = 0.9
    if answer is None:
        label, value = _extract_label_value(labels)
        if label and value:
            questions = _label_question(label)
            answer = value
            confidence = 0.75
        else:
            questions, answer = _extract_paragraph_fact(evidence_text)
            confidence = 0.7
    if answer is None:
        return _outcome(
            status="abstain",
            reason_code="UNSUPPORTED_INPUT_SURFACE",
            evidence_digests=evidence_digests,
            source_digest=source_digest,
        )
    if not _grounded(answer, evidence_text):
        return _outcome(
            status="abstain",
            reason_code="ANSWER_NOT_GROUNDED",
            evidence_digests=evidence_digests,
            source_digest=source_digest,
        )
    missing: list[str] = []
    if not source:
        missing.append("source")
    if not questions:
        missing.append("question_patterns")
    if confidence >= 1.0:
        return _outcome(
            status="abstain",
            reason_code="CONFIDENCE_ONE_FORBIDDEN",
            evidence_digests=evidence_digests,
            source_digest=source_digest,
        )
    if missing:
        return _outcome(
            status="needs_confirmation",
            reason_code=";".join(f"{field.upper()}_REQUIRED" for field in missing),
            evidence_digests=evidence_digests,
            source_digest=source_digest,
            missing_fields=missing,
            confidence=confidence,
        )
    candidate = _candidate_draft(
        questions=questions,
        answer=answer,
        source=source or "",
        labels=labels,
        evidence_text=evidence_text,
        confidence=confidence,
    )
    if not _validate_candidate_draft(candidate):
        return _outcome(
            status="needs_confirmation",
            reason_code="CANDIDATE_SCHEMA_INVALID",
            evidence_digests=evidence_digests,
            source_digest=source_digest,
            missing_fields=["candidate_schema"],
            confidence=confidence,
        )
    return _outcome(
        status="draft_ready",
        reason_code="DRAFT_READY",
        candidate_draft=candidate,
        evidence_digests=evidence_digests,
        source_digest=source_digest,
        confidence=confidence,
    )
