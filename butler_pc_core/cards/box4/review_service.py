"""Fail-closed Box4 document review service.

The service treats document contents as untrusted data and validates the local
model output before returning anything to the UI.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import asdict, dataclass
from typing import Any, List, Optional

from butler_pc_core.dlp.runtime import (
    SAFE_SECRET_REPLACEMENT,
    redact_fail_closed as _redact_secret_value,
)
from butler_pc_core.prompts.card_renderer import render_card_user_prompt
from butler_pc_core.prompts.cards import load_card_prompt
from butler_pc_core.runtime.json_grammar import (
    GrammarUnavailable,
    build_json_schema_grammar,
    normalize_model_response_to_text,
    stable_json_dumps,
    stable_schema_digest,
    structured_generation_telemetry,
)


_LOG = logging.getLogger(__name__)

SCHEMA_VERSION = "card_04.document_review.v1"
ISSUE_TYPES = frozenset({"MISSING", "ERROR", "INCONSISTENCY", "STYLE", "SUGGESTION"})
CONFIDENCES = frozenset({"HIGH", "MEDIUM", "LOW"})
REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "issues", "overall_score", "summary", "review_required", "warnings"}
)
REQUIRED_ISSUE_KEYS = frozenset({"location", "issue_type", "original_text", "suggestion", "confidence"})
MAX_ISSUES = 50
MAX_TEXT_CHARS = 300
MAX_SUMMARY_CHARS = 1200

BOX4_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": [SCHEMA_VERSION]},
        "issues": {
            "type": "array",
            "maxItems": MAX_ISSUES,
            "items": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "issue_type": {"type": "string", "enum": sorted(ISSUE_TYPES)},
                    "original_text": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "confidence": {"type": "string", "enum": sorted(CONFIDENCES)},
                },
                "required": sorted(REQUIRED_ISSUE_KEYS),
                "additionalProperties": False,
            },
        },
        "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "summary": {"type": "string"},
        "review_required": {"type": "boolean"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": sorted(REQUIRED_TOP_LEVEL_KEYS),
    "additionalProperties": False,
}
BOX4_SCHEMA_DIGEST = stable_schema_digest(BOX4_JSON_SCHEMA)

@dataclass(frozen=True)
class DocumentReviewInput:
    target_document: str
    reference_documents: List[str]
    strict_mode: bool = True
    request_id: Optional[str] = None
    source_kind: str = "ui"


@dataclass(frozen=True)
class DocumentReviewResult:
    schema_version: str
    issues: List[dict[str, str]]
    overall_score: int
    summary: str
    review_required: bool
    warnings: List[str]
    raw_log_zero: bool = True
    external_send_zero: bool = True

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _safe_error_result(reason_code: str) -> DocumentReviewResult:
    return DocumentReviewResult(
        schema_version=SCHEMA_VERSION,
        issues=[],
        overall_score=0,
        summary="문서검토 결과를 안전하게 확정하지 못했습니다.",
        review_required=True,
        warnings=[reason_code],
    )


def _log_structured_telemetry(event: dict[str, object]) -> None:
    _LOG.info("structured_generation_telemetry %s", stable_json_dumps(event))


def _emit_structured_generation_telemetry(
    response_text: str,
    *,
    method_selected: str,
    model_client: Any,
    grammar_applied: bool,
    reason_code: str = "",
) -> None:
    _log_structured_telemetry(
        structured_generation_telemetry(
            response_text,
            event="structured_generation",
            card_mode="4",
            schema_id=SCHEMA_VERSION,
            schema_digest=BOX4_SCHEMA_DIGEST,
            grammar_required=True,
            grammar_applied=grammar_applied,
            method_selected=method_selected,
            model_client_class=type(model_client).__name__,
            reason_code=reason_code,
        )
    )


def _normalize_and_emit_model_response(
    raw: Any,
    *,
    model_client: Any,
    method_selected: str,
    grammar: Any | None,
) -> str:
    text = normalize_model_response_to_text(raw)
    _emit_structured_generation_telemetry(
        text,
        method_selected=method_selected,
        model_client=model_client,
        grammar_applied=grammar is not None,
    )
    return text


def _extract_json_object(text: str) -> dict[str, Any]:
    source = str(text or "")
    start = source.find("{")
    if start < 0:
        raise ValueError("MODEL_JSON_NOT_FOUND")

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(source)):
        char = source[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = source[start : idx + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise ValueError("MODEL_JSON_INVALID") from exc
                if not isinstance(parsed, dict):
                    raise ValueError("MODEL_JSON_NOT_OBJECT")
                return parsed
    raise ValueError("MODEL_JSON_UNCLOSED")


def _require_string(value: Any, reason_code: str, *, max_len: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        raise ValueError(reason_code)
    if len(value) > max_len:
        raise ValueError(f"{reason_code}_TOO_LONG")
    return _redact_secret_value(value)


def _require_exact_keys(obj: dict[str, Any], required: frozenset[str], reason_code: str) -> None:
    if set(obj.keys()) != set(required):
        raise ValueError(reason_code)


def _validate_review_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _require_exact_keys(payload, REQUIRED_TOP_LEVEL_KEYS, "SCHEMA_KEYS_INVALID")

    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("SCHEMA_VERSION_INVALID")

    raw_score = payload["overall_score"]
    if isinstance(raw_score, bool) or not isinstance(raw_score, int):
        raise ValueError("OVERALL_SCORE_INVALID")
    if raw_score < 0 or raw_score > 100:
        raise ValueError("OVERALL_SCORE_OUT_OF_RANGE")

    summary = _require_string(
        payload["summary"],
        "SUMMARY_INVALID",
        max_len=MAX_SUMMARY_CHARS,
    )

    raw_review_required = payload["review_required"]
    if not isinstance(raw_review_required, bool):
        raise ValueError("REVIEW_REQUIRED_INVALID")

    raw_warnings = payload["warnings"]
    if not isinstance(raw_warnings, list):
        raise ValueError("WARNINGS_INVALID")
    warnings: list[str] = []
    for item in raw_warnings:
        warnings.append(_require_string(item, "WARNING_INVALID", max_len=120))

    raw_issues = payload["issues"]
    if not isinstance(raw_issues, list):
        raise ValueError("ISSUES_INVALID")
    if len(raw_issues) > MAX_ISSUES:
        raise ValueError("ISSUES_TOO_MANY")

    issues: list[dict[str, str]] = []
    for item in raw_issues:
        if not isinstance(item, dict):
            raise ValueError("ISSUE_INVALID")
        _require_exact_keys(item, REQUIRED_ISSUE_KEYS, "ISSUE_KEYS_INVALID")
        issue_type = item["issue_type"]
        if issue_type not in ISSUE_TYPES:
            raise ValueError("ISSUE_TYPE_INVALID")
        confidence = item["confidence"]
        if confidence not in CONFIDENCES:
            raise ValueError("CONFIDENCE_INVALID")
        issues.append(
            {
                "location": _require_string(item["location"], "LOCATION_INVALID"),
                "issue_type": str(issue_type),
                "original_text": _require_string(item["original_text"], "ORIGINAL_TEXT_INVALID"),
                "suggestion": _require_string(item["suggestion"], "SUGGESTION_INVALID"),
                "confidence": str(confidence),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "issues": issues,
        "overall_score": raw_score,
        "summary": summary,
        "review_required": raw_review_required,
        "warnings": warnings,
    }


def _call_model_client(model_client: Any, prompt: str, *, grammar: Any | None = None) -> str:
    if model_client is None:
        raise ValueError("MODEL_CLIENT_REQUIRED")
    if hasattr(model_client, "generate_with_cancel"):
        try:
            raw = model_client.generate_with_cancel(
                prompt,
                threading.Event(),
                max_tokens=2048,
                grammar=grammar,
            )
        except TypeError as exc:
            if grammar is not None:
                raise GrammarUnavailable("MODEL_CLIENT_GRAMMAR_UNSUPPORTED") from exc
            raise
        return _normalize_and_emit_model_response(
            raw,
            model_client=model_client,
            method_selected="generate_with_cancel",
            grammar=grammar,
        )
    if hasattr(model_client, "generate"):
        try:
            raw = model_client.generate(prompt, max_tokens=2048, grammar=grammar)
        except TypeError as exc:
            if grammar is not None:
                raise GrammarUnavailable("MODEL_CLIENT_GRAMMAR_UNSUPPORTED") from exc
            raise
        return _normalize_and_emit_model_response(
            raw,
            model_client=model_client,
            method_selected="generate",
            grammar=grammar,
        )
    if hasattr(model_client, "generate_text"):
        if grammar is not None:
            raise GrammarUnavailable("MODEL_CLIENT_GRAMMAR_UNSUPPORTED")
        raw = model_client.generate_text(prompt, max_new_tokens=2048)
        return _normalize_and_emit_model_response(
            raw,
            model_client=model_client,
            method_selected="generate_text",
            grammar=grammar,
        )
    if callable(model_client):
        if grammar is not None:
            raise GrammarUnavailable("MODEL_CLIENT_GRAMMAR_UNSUPPORTED")
        raw = model_client(prompt)
        return _normalize_and_emit_model_response(
            raw,
            model_client=model_client,
            method_selected="callable",
            grammar=grammar,
        )
    raise ValueError("MODEL_CLIENT_UNSUPPORTED")


def _generate_review_json(model_client: Any, prompt: str) -> str:
    try:
        grammar = build_json_schema_grammar(BOX4_JSON_SCHEMA, required=True)
    except GrammarUnavailable as exc:
        raise ValueError("GRAMMAR_UNAVAILABLE") from exc
    try:
        return _call_model_client(model_client, prompt, grammar=grammar)
    except GrammarUnavailable as exc:
        raise ValueError("GRAMMAR_UNAVAILABLE") from exc


def review_document(req: DocumentReviewInput, *, model_client: Any) -> DocumentReviewResult:
    if not isinstance(req, DocumentReviewInput):
        return _safe_error_result("REQUEST_SCHEMA_INVALID")
    target_document = str(req.target_document or "")
    reference_documents = [str(item) for item in (req.reference_documents or []) if str(item).strip()]
    if not target_document.strip():
        return _safe_error_result("TARGET_DOCUMENT_EMPTY")

    model_output = ""
    try:
        card = load_card_prompt("4")
        user_prompt = render_card_user_prompt(
            card,
            query=target_document,
            file_texts=reference_documents,
        )
        system_prompt = str(card.get("system_prompt") or "")
        prompt = (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n/no_think\n{user_prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        model_output = _generate_review_json(model_client, prompt)
        payload = _validate_review_payload(_extract_json_object(model_output))
    except ValueError as exc:
        reason_code = str(exc) or "DOCUMENT_REVIEW_FAILED"
        _emit_structured_generation_telemetry(
            model_output,
            method_selected="validation",
            model_client=model_client,
            grammar_applied=bool(model_output),
            reason_code=reason_code,
        )
        return _safe_error_result(reason_code)
    except Exception:
        _emit_structured_generation_telemetry(
            model_output,
            method_selected="validation",
            model_client=model_client,
            grammar_applied=bool(model_output),
            reason_code="DOCUMENT_REVIEW_FAILED",
        )
        return _safe_error_result("DOCUMENT_REVIEW_FAILED")

    return DocumentReviewResult(**payload)
