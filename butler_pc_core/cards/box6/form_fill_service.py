"""Fail-closed Box6 form-fill service with JSON Schema grammar enforcement."""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import asdict, dataclass
from typing import Any, List, Optional

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

SCHEMA_VERSION = "card_06.form_fill.v1"
CONFIDENCES = frozenset({"HIGH", "MEDIUM", "LOW", "UNFILLED"})
REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "filled_form", "field_mappings", "unfilled_fields", "review_required", "warnings"}
)
REQUIRED_MAPPING_KEYS = frozenset({"target_label", "output_value", "confidence", "source_ref", "reason_code"})
MAX_MAPPINGS = 80
MAX_TEXT_CHARS = 20000
MAX_FIELD_CHARS = 2000
SAFE_SECRET_REPLACEMENT = "[민감정보 원문 생략]"

BOX6_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": [SCHEMA_VERSION]},
        "filled_form": {"type": "string"},
        "field_mappings": {
            "type": "array",
            "maxItems": MAX_MAPPINGS,
            "items": {
                "type": "object",
                "properties": {
                    "target_label": {"type": "string"},
                    "output_value": {"type": "string"},
                    "confidence": {"type": "string", "enum": sorted(CONFIDENCES)},
                    "source_ref": {"type": "string"},
                    "reason_code": {"type": "string"},
                },
                "required": sorted(REQUIRED_MAPPING_KEYS),
                "additionalProperties": False,
            },
        },
        "unfilled_fields": {"type": "array", "items": {"type": "string"}},
        "review_required": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": sorted(REQUIRED_TOP_LEVEL_KEYS),
    "additionalProperties": False,
}
BOX6_SCHEMA_DIGEST = stable_schema_digest(BOX6_JSON_SCHEMA)

_SECRET_LABEL_PATTERN = (
    r"비밀번호|비번|암호|패스워드|토큰|시크릿|"
    r"API[ \t_-]*키|에이피아이[ \t_-]*키|인증[ \t_-]*키|보안[ \t_-]*키|개인[ \t_-]*키|"
    r"secret|password|token|api[ \t_-]*key|access[ \t_-]*key|auth[ \t_-]*key|"
    r"client[ \t_-]*secret|private[ \t_-]*key|seed[ \t_-]*phrase"
)
_SECRET_VALUE_RE = re.compile(
    rf"(?:"
    rf"sk-[A-Za-z0-9._-]{{10,}}|"
    rf"AKIA[0-9A-Z]{{16}}|"
    rf"-----BEGIN[ \t]+[A-Z ]*PRIVATE KEY-----|"
    rf"(?:{_SECRET_LABEL_PATTERN})[ \t]*(?:는|은|[:=：])[ \t]*[^\n\r,;]{{4,}}|"
    rf"\b\d{{6}}-\d{{7}}\b"
    rf")",
    re.IGNORECASE,
)
_SECRET_LABEL_RE = re.compile(rf"(?:{_SECRET_LABEL_PATTERN})", re.IGNORECASE)
_UNFILLED_VALUE_RE = re.compile(r"^(?:UNFILLED|\[?확인\s*필요\]?|미기입)$", re.IGNORECASE)


@dataclass(frozen=True)
class FormFillInput:
    blank_form: str
    data_documents: List[str]
    strict_mode: bool = True
    request_id: Optional[str] = None
    source_kind: str = "ui"


@dataclass(frozen=True)
class FormFillResult:
    schema_version: str
    filled_form: str
    field_mappings: List[dict[str, str]]
    unfilled_fields: List[str]
    review_required: List[str]
    warnings: List[str]

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _safe_error_result(reason_code: str) -> FormFillResult:
    return FormFillResult(
        schema_version=SCHEMA_VERSION,
        filled_form="",
        field_mappings=[],
        unfilled_fields=[],
        review_required=["결과 형식 확인"],
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
            card_mode="6",
            schema_id=SCHEMA_VERSION,
            schema_digest=BOX6_SCHEMA_DIGEST,
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


def _redact_secret_value(value: str) -> str:
    return _SECRET_VALUE_RE.sub(SAFE_SECRET_REPLACEMENT, value)


def _is_secret_target_label(value: str) -> bool:
    return bool(_SECRET_LABEL_RE.search(value or ""))


def _label_key(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


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


def _require_exact_keys(obj: dict[str, Any], required: frozenset[str], reason_code: str) -> None:
    if set(obj.keys()) != set(required):
        raise ValueError(reason_code)


def _require_string(value: Any, reason_code: str, *, max_len: int = MAX_FIELD_CHARS) -> str:
    if not isinstance(value, str):
        raise ValueError(reason_code)
    if len(value) > max_len:
        raise ValueError(f"{reason_code}_TOO_LONG")
    return _redact_secret_value(value)


def _require_string_list(value: Any, reason_code: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(reason_code)
    return [_require_string(item, f"{reason_code}_ITEM_INVALID") for item in value]


def _validate_form_fill_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _require_exact_keys(payload, REQUIRED_TOP_LEVEL_KEYS, "SCHEMA_KEYS_INVALID")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("SCHEMA_VERSION_INVALID")

    filled_form = _require_string(payload["filled_form"], "FILLED_FORM_INVALID", max_len=MAX_TEXT_CHARS)
    unfilled_fields = _require_string_list(payload["unfilled_fields"], "UNFILLED_FIELDS_INVALID")
    review_required = _require_string_list(payload["review_required"], "REVIEW_REQUIRED_INVALID")
    warnings = _require_string_list(payload["warnings"], "WARNINGS_INVALID")
    unfilled_field_keys = {_label_key(item) for item in unfilled_fields}
    review_required_keys = {_label_key(item) for item in review_required}

    raw_mappings = payload["field_mappings"]
    if not isinstance(raw_mappings, list):
        raise ValueError("FIELD_MAPPINGS_INVALID")
    if len(raw_mappings) > MAX_MAPPINGS:
        raise ValueError("FIELD_MAPPINGS_TOO_MANY")

    field_mappings: list[dict[str, str]] = []
    for item in raw_mappings:
        if not isinstance(item, dict):
            raise ValueError("FIELD_MAPPING_INVALID")
        if "source_excerpt" in item or "review_required" in item:
            raise ValueError("LEGACY_MAPPING_SCHEMA")
        _require_exact_keys(item, REQUIRED_MAPPING_KEYS, "FIELD_MAPPING_KEYS_INVALID")
        confidence = item["confidence"]
        if confidence not in CONFIDENCES:
            raise ValueError("CONFIDENCE_INVALID")
        target_label = _require_string(item["target_label"], "TARGET_LABEL_INVALID")
        output_value = _require_string(item["output_value"], "OUTPUT_VALUE_INVALID")
        if _is_secret_target_label(target_label):
            raw_output_value = str(item["output_value"]).strip()
            label_key = _label_key(target_label)
            is_unfilled_value = not raw_output_value or bool(_UNFILLED_VALUE_RE.match(raw_output_value))
            is_listed_unfilled = label_key in unfilled_field_keys
            is_review_listed = label_key in review_required_keys
            is_quarantined = is_listed_unfilled and (is_review_listed or bool(review_required))
            if not is_unfilled_value and not is_quarantined:
                raise ValueError("SENSITIVE_FIELD_AUTOFILL_BLOCKED")
            if not review_required and not is_listed_unfilled:
                raise ValueError("SENSITIVE_FIELD_AUTOFILL_BLOCKED")
            if not is_unfilled_value:
                output_value = SAFE_SECRET_REPLACEMENT
        field_mappings.append(
            {
                "target_label": target_label,
                "output_value": output_value,
                "confidence": str(confidence),
                "source_ref": _require_string(item["source_ref"], "SOURCE_REF_INVALID"),
                "reason_code": _require_string(item["reason_code"], "REASON_CODE_INVALID"),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "filled_form": filled_form,
        "field_mappings": field_mappings,
        "unfilled_fields": unfilled_fields,
        "review_required": review_required,
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


def _generate_form_fill_json(model_client: Any, prompt: str) -> str:
    try:
        grammar = build_json_schema_grammar(BOX6_JSON_SCHEMA, required=True)
    except GrammarUnavailable as exc:
        raise ValueError("GRAMMAR_UNAVAILABLE") from exc
    try:
        return _call_model_client(model_client, prompt, grammar=grammar)
    except GrammarUnavailable as exc:
        raise ValueError("GRAMMAR_UNAVAILABLE") from exc


def fill_form(req: FormFillInput, *, model_client: Any) -> FormFillResult:
    if not isinstance(req, FormFillInput):
        return _safe_error_result("REQUEST_SCHEMA_INVALID")
    blank_form = str(req.blank_form or "")
    data_documents = [str(item) for item in (req.data_documents or []) if str(item).strip()]
    if not blank_form.strip():
        return _safe_error_result("BLANK_FORM_EMPTY")

    model_output = ""
    try:
        card = load_card_prompt("6")
        user_prompt = render_card_user_prompt(
            card,
            query=blank_form,
            file_texts=data_documents,
        )
        system_prompt = str(card.get("system_prompt") or "")
        prompt = (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n/no_think\n{user_prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        model_output = _generate_form_fill_json(model_client, prompt)
        payload = _validate_form_fill_payload(_extract_json_object(model_output))
    except ValueError as exc:
        reason_code = str(exc) or "FORM_FILL_FAILED"
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
            reason_code="FORM_FILL_FAILED",
        )
        return _safe_error_result("FORM_FILL_FAILED")

    return FormFillResult(**payload)
