"""Grammar-constrained Box6 form-fill service."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass
from typing import Any, List, Optional

from butler_pc_core.prompts.card_renderer import render_card_user_prompt
from butler_pc_core.prompts.cards import load_card_prompt
from butler_pc_core.runtime.json_grammar import GrammarUnavailable, build_json_schema_grammar, stable_schema_digest

SCHEMA_VERSION = "card_06.form_fill.v1"
CONFIDENCES = frozenset({"HIGH", "MEDIUM", "LOW", "UNFILLED"})
REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "filled_form", "field_mappings", "unfilled_fields", "review_required", "warnings"}
)
REQUIRED_MAPPING_KEYS = frozenset({"target_label", "output_value", "confidence", "source_ref", "reason_code"})
MAX_MAPPINGS = 80
MAX_TEXT_CHARS = 20_000
MAX_FIELD_TEXT_CHARS = 500
SAFE_SECRET_REPLACEMENT = "[민감정보 원문 생략]"
UNFILLED_VALUES = {"", "UNFILLED", "[미기입]", "[확인 필요]", "검토 필요", "미기입", SAFE_SECRET_REPLACEMENT}

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
                "required": ["target_label", "output_value", "confidence", "source_ref", "reason_code"],
                "additionalProperties": False,
            },
        },
        "unfilled_fields": {"type": "array", "items": {"type": "string"}},
        # PR #841 frontend contract expects a string-array top-level review_required.
        "review_required": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["schema_version", "filled_form", "field_mappings", "unfilled_fields", "review_required", "warnings"],
    "additionalProperties": False,
}
BOX6_SCHEMA_DIGEST = stable_schema_digest(BOX6_JSON_SCHEMA)

_SECRET_VALUE_RE = re.compile(
    r"(?:"
    r"sk-(?:proj-)?[A-Za-z0-9._-]{10,}|"
    r"AKIA[0-9A-Z]{16}|"
    r"ASIA[0-9A-Z]{16}|"
    r"-----BEGIN[ \t]+[A-Z ]*PRIVATE KEY-----|"
    r"(?:비밀번호|비번|암호|패스워드|password|token|api[ \t_-]*key|private[ \t_-]*key|client[ \t_-]*secret)"
    r"[ \t]*(?:는|은|[:=：]|->|=>)[ \t]*[^\s,;'\"<>]{2,}"
    r")",
    re.IGNORECASE,
)
_SECRET_LABEL_RE = re.compile(
    r"(?:비밀번호|비번|암호|패스워드|API\s*키|에이피아이\s*키|토큰|인증\s*키|보안\s*키|개인\s*키|"
    r"secret|password|token|api\s*key|client\s*secret|private\s*key)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FormFillInput:
    blank_form: str
    our_data_documents: List[str]
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
    raw_log_zero: bool = True
    external_send_zero: bool = True

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _safe_error_result(reason_code: str) -> FormFillResult:
    return FormFillResult(
        schema_version=SCHEMA_VERSION,
        filled_form="",
        field_mappings=[],
        unfilled_fields=[],
        review_required=[],
        warnings=[reason_code],
    )


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
                try:
                    parsed = json.loads(source[start : idx + 1])
                except json.JSONDecodeError as exc:
                    raise ValueError("MODEL_JSON_INVALID") from exc
                if not isinstance(parsed, dict):
                    raise ValueError("MODEL_JSON_NOT_OBJECT")
                return parsed
    raise ValueError("MODEL_JSON_UNCLOSED")


def normalize_model_response_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        raise ValueError("MODEL_RESPONSE_UNSUPPORTED")
    choices = value.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("MODEL_RESPONSE_CHOICES_MISSING")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("MODEL_RESPONSE_CHOICE_INVALID")
    if isinstance(first.get("text"), str):
        return first["text"]
    message = first.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    raise ValueError("MODEL_RESPONSE_TEXT_MISSING")


def _require_string(value: Any, reason_code: str, *, max_len: int = MAX_FIELD_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        raise ValueError(reason_code)
    if len(value) > max_len:
        raise ValueError(f"{reason_code}_TOO_LONG")
    return _redact_secret_value(value)


def _redact_secret_value(value: str) -> str:
    return _SECRET_VALUE_RE.sub(SAFE_SECRET_REPLACEMENT, value)


def _require_string_list(value: Any, reason_code: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(reason_code)
    return [_require_string(item, f"{reason_code}_ITEM") for item in value]


def _require_exact_keys(obj: dict[str, Any], required: frozenset[str], reason_code: str) -> None:
    if set(obj.keys()) != set(required):
        raise ValueError(reason_code)


def _is_secret_label(value: str) -> bool:
    return bool(_SECRET_LABEL_RE.search(value))


def _is_safe_unfilled(value: str) -> bool:
    return value.strip() in UNFILLED_VALUES


def _validate_secret_policy(field_mappings: list[dict[str, str]], unfilled_fields: list[str], review_required: list[str]) -> None:
    unfilled = {field.strip() for field in unfilled_fields}
    review = {field.strip() for field in review_required}
    for mapping in field_mappings:
        target = mapping["target_label"].strip()
        output = mapping["output_value"].strip()
        if _is_secret_label(target):
            if not _is_safe_unfilled(output):
                raise ValueError("SECRET_AUTOFILL_FORBIDDEN")
            if target not in unfilled and target not in review:
                raise ValueError("SECRET_REVIEW_REQUIRED")


def _validate_form_fill_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _require_exact_keys(payload, REQUIRED_TOP_LEVEL_KEYS, "SCHEMA_KEYS_INVALID")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("SCHEMA_VERSION_INVALID")
    filled_form = _require_string(payload["filled_form"], "FILLED_FORM_INVALID", max_len=MAX_TEXT_CHARS)
    raw_mappings = payload["field_mappings"]
    if not isinstance(raw_mappings, list) or len(raw_mappings) > MAX_MAPPINGS:
        raise ValueError("FIELD_MAPPINGS_INVALID")
    field_mappings: list[dict[str, str]] = []
    for item in raw_mappings:
        if not isinstance(item, dict):
            raise ValueError("FIELD_MAPPING_INVALID")
        _require_exact_keys(item, REQUIRED_MAPPING_KEYS, "FIELD_MAPPING_KEYS_INVALID")
        confidence = item["confidence"]
        if confidence not in CONFIDENCES:
            raise ValueError("CONFIDENCE_INVALID")
        field_mappings.append(
            {
                "target_label": _require_string(item["target_label"], "TARGET_LABEL_INVALID"),
                "output_value": _require_string(item["output_value"], "OUTPUT_VALUE_INVALID"),
                "confidence": str(confidence),
                "source_ref": _require_string(item["source_ref"], "SOURCE_REF_INVALID"),
                "reason_code": _require_string(item["reason_code"], "REASON_CODE_INVALID"),
            }
        )
    unfilled_fields = _require_string_list(payload["unfilled_fields"], "UNFILLED_FIELDS_INVALID")
    review_required = _require_string_list(payload["review_required"], "REVIEW_REQUIRED_INVALID")
    warnings = _require_string_list(payload["warnings"], "WARNINGS_INVALID")
    _validate_secret_policy(field_mappings, unfilled_fields, review_required)
    return {
        "schema_version": SCHEMA_VERSION,
        "filled_form": filled_form,
        "field_mappings": field_mappings,
        "unfilled_fields": unfilled_fields,
        "review_required": review_required,
        "warnings": warnings,
    }


def _generate_form_fill_json(model_client: Any, prompt: str) -> str:
    try:
        grammar = build_json_schema_grammar(BOX6_JSON_SCHEMA, required=True)
    except GrammarUnavailable as exc:
        raise ValueError("GRAMMAR_UNAVAILABLE") from exc
    if model_client is None:
        raise ValueError("MODEL_CLIENT_REQUIRED")
    if hasattr(model_client, "generate_with_cancel"):
        return normalize_model_response_to_text(
            model_client.generate_with_cancel(prompt, threading.Event(), max_tokens=2048, grammar=grammar)
        )
    if hasattr(model_client, "generate"):
        return normalize_model_response_to_text(model_client.generate(prompt, max_tokens=2048, grammar=grammar))
    raise ValueError("GRAMMAR_UNAVAILABLE")


def fill_form(req: FormFillInput, *, model_client: Any) -> FormFillResult:
    if not isinstance(req, FormFillInput):
        return _safe_error_result("REQUEST_SCHEMA_INVALID")
    blank_form = str(req.blank_form or "")
    our_data_documents = [str(item) for item in (req.our_data_documents or []) if str(item).strip()]
    if not blank_form.strip():
        return _safe_error_result("BLANK_FORM_EMPTY")
    try:
        card = load_card_prompt("6")
        user_prompt = render_card_user_prompt(card, query=blank_form, file_texts=our_data_documents)
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
        return _safe_error_result(reason_code)
    except Exception:
        return _safe_error_result("FORM_FILL_FAILED")
    return FormFillResult(**payload)
