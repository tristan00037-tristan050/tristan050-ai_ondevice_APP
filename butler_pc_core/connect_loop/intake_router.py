"""Box1 intake router v3.6.

This module creates an attachment-aware *decision only*. It never calls box,
helper, company-fact, company-format, or policy endpoints. `target_endpoint` is
only populated when the destination is dispatchable under the current bootstrap
state and, for company facts, when a structured candidate payload has already
passed the real CompanyFactCandidateRequest boundary. `candidate_endpoint_hint`
is a non-dispatchable hint for UI/next-step guidance.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .attachment_features import AttachmentFeatureBundle, feature_summary_for_decision, sha256_text, stable_json_digest

SCHEMA_VERSION = "intake_decision.v1"
DECISION_ID_SCHEMA_VERSION = "intake_decision_id.v2"

DEST_BOX5 = "box5_accounting_classify"
DEST_BOX3 = "box3_draft_from_material"
DEST_BOX2 = "box2_form_convert"
DEST_BOX4 = "box4_edit_attachment"
DEST_BOX6 = "box6_fill_external_form"
DEST_BOX7 = "box7_meeting_minutes"
DEST_BOX8 = "box8_data_insight"
DEST_COMPANY_FACT = "company_fact_candidate"
DEST_COMPANY_FORMAT = "company_format_candidate"
DEST_ASK = "ask_followup"
DEST_NONE = "none"

REAL_ENDPOINTS: dict[str, tuple[str, str]] = {
    DEST_BOX5: ("5", "POST /accounting/classify"),
    DEST_BOX3: ("3", "POST /v1/cards/3/draft"),
    DEST_BOX2: ("2", "POST /v1/cards/2/rewrite"),
    DEST_COMPANY_FACT: ("company_fact", "POST /v1/company-facts/candidates"),
}

NON_CALLABLE_BOXES: dict[str, tuple[str, str]] = {
    DEST_BOX4: ("4", "ENDPOINT_NOT_IMPLEMENTED"),
    DEST_BOX6: ("6", "ENDPOINT_NOT_IMPLEMENTED"),
    DEST_BOX7: ("7", "ENDPOINT_NOT_IMPLEMENTED"),
    DEST_BOX8: ("8", "ENDPOINT_NOT_IMPLEMENTED"),
    DEST_COMPANY_FORMAT: ("company_format", "ADMIN_FORMAT_REGISTRATION_REQUIRED"),
    DEST_ASK: ("none", "ASK_FOLLOWUP"),
    DEST_NONE: ("none", "ASK_FOLLOWUP"),
}

CANDIDATE_ENDPOINT_HINT = "POST /v1/company-facts/candidates"
ALLOWED_TARGET_ENDPOINTS = {"none", *(endpoint for _, endpoint in REAL_ENDPOINTS.values())}

POLICY_READY_METHOD_ACTIVE_POLICY = "active_policy_presence"
POLICY_READY_METHOD_OVERRIDE = "test_override"
POLICY_READY_METHOD_FAIL_CLOSED = "fail_closed_unavailable"

_THRESHOLD = 0.70
_AMBIGUITY_DELTA = 0.12
_STRONG_FILE_SCORE = 0.78
_MEDIUM_FILE_SCORE = 0.66

_PATH_OR_FILENAME_RE = re.compile(
    r"(/Users/|/home/|/Volumes/|[A-Za-z]:\\|file://|\.(xlsx|xls|csv|docx|pdf|hwp|hwpx|m4a|mp3|wav))",
    re.I,
)

INSPECTED_RAW_FIELDS = (
    "reason_code",
    "next_action",
    "candidate_endpoint_hint",
    "followup_prompt",
    "fail_class",
)


class IntakeContractError(ValueError):
    def __init__(self, fail_class: str) -> None:
        super().__init__(fail_class)
        self.fail_class = fail_class


class CompanyFactSchemaUnavailable(IntakeContractError):
    def __init__(self) -> None:
        super().__init__("COMPANY_FACT_SCHEMA_UNAVAILABLE")


@dataclass(frozen=True)
class DestinationScore:
    destination: str
    score: float
    reason_code: str
    attachment_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "score": round(self.score, 4),
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class PolicyBootstrapStatus:
    ready: bool
    method: str
    fail_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ready": self.ready, "method": self.method, "fail_class": self.fail_class}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _runtime_digest(runtime_text: str | None) -> str | None:
    if runtime_text is None:
        return None
    return sha256_text(runtime_text)


def _text_boosts(runtime_text: str | None) -> dict[str, float]:
    text = " ".join((runtime_text or "").casefold().split())
    boosts = {dest: 0.0 for dest in [DEST_BOX5, DEST_BOX3, DEST_BOX2, DEST_BOX4, DEST_BOX6, DEST_BOX7, DEST_BOX8, DEST_COMPANY_FACT, DEST_COMPANY_FORMAT]}
    if any(term in text for term in ("분개", "회계", "통장", "거래내역", "계정과목")):
        boosts[DEST_BOX5] += 0.18
    if any(term in text for term in ("초안", "보고서", "문안", "작성", "새 문서")):
        boosts[DEST_BOX3] += 0.18
    if any(term in text for term in ("우리 양식", "변환", "서식", "포맷")):
        boosts[DEST_BOX2] += 0.22
    if any(term in text for term in ("수정", "보완", "고쳐", "편집")):
        boosts[DEST_BOX4] += 0.18
    if any(term in text for term in ("채워", "기입", "빈칸", "작성란")):
        boosts[DEST_BOX6] += 0.12
    if any(term in text for term in ("회의록", "녹음", "음성", "전사")):
        boosts[DEST_BOX7] += 0.14
    if any(term in text for term in ("분석", "통계", "데이터셋", "인사이트")):
        boosts[DEST_BOX8] += 0.15
    if any(term in text for term in ("회사 규정", "내규", "지식", "faq", "규칙")):
        boosts[DEST_COMPANY_FACT] += 0.15
    if any(term in text for term in ("회사 양식", "양식 등록", "서식 등록", "템플릿")):
        boosts[DEST_COMPANY_FORMAT] += 0.15
    return boosts


def _score_single_attachment(feature: dict[str, Any], runtime_text: str | None) -> list[DestinationScore]:
    kind = str(feature.get("file_kind") or "unknown_binary")
    fail = feature.get("extractor_fail_class")
    boosts = _text_boosts(runtime_text)
    file_digest = feature.get("file_digest") if isinstance(feature.get("file_digest"), str) else None

    base: list[DestinationScore]
    if fail:
        base = [DestinationScore(DEST_ASK, 0.72, str(fail), file_digest)]
    elif kind == "bank_statement_table":
        base = [DestinationScore(DEST_BOX5, _STRONG_FILE_SCORE, "FILE_HEADER_ACCOUNTING_LEDGER_MATCH", file_digest)]
    elif kind == "generic_dataset":
        base = [DestinationScore(DEST_BOX8, 0.72, "GENERIC_NUMERIC_DATASET", file_digest)]
    elif kind == "company_policy_doc":
        base = [DestinationScore(DEST_COMPANY_FACT, 0.74, "COMPANY_POLICY_DOC_SIGNAL", file_digest)]
    elif kind == "company_format_template":
        # If text explicitly asks to fill an external form, Box6 is possible, but
        # admin format candidate remains the safe default for definition-like docs.
        dest = DEST_BOX6 if boosts.get(DEST_BOX6, 0.0) >= 0.12 else DEST_COMPANY_FORMAT
        base = [DestinationScore(dest, 0.72, "COMPANY_FORMAT_TEMPLATE_SIGNAL", file_digest)]
    elif kind == "external_doc_to_convert":
        base = [DestinationScore(DEST_BOX2, 0.72, "EXTERNAL_DOC_TO_CONVERT_SIGNAL", file_digest)]
    elif kind == "draft_source_material":
        base = [DestinationScore(DEST_BOX3, 0.72, "DRAFT_SOURCE_MATERIAL_SIGNAL", file_digest)]
    elif kind == "audio_meeting":
        base = [DestinationScore(DEST_BOX7, _STRONG_FILE_SCORE, "AUDIO_MEETING_SIGNAL", file_digest)]
    else:
        base = [DestinationScore(DEST_ASK, 0.55, "UNSUPPORTED_OR_AMBIGUOUS_ATTACHMENT", file_digest)]

    # Add text signal boosts to all relevant destinations, preserving the base reason.
    scored = {item.destination: item for item in base}
    for dest, boost in boosts.items():
        if boost <= 0:
            continue
        previous = scored.get(dest)
        if previous is not None:
            scored[dest] = DestinationScore(dest, min(1.0, previous.score + boost), previous.reason_code, file_digest)
        else:
            scored[dest] = DestinationScore(dest, min(1.0, 0.35 + boost), "TEXT_HINT_BOOST", file_digest)
    return sorted(scored.values(), key=lambda item: item.score, reverse=True)


def _combine_scores(bundle: AttachmentFeatureBundle, runtime_text: str | None) -> tuple[str, float, str, list[dict[str, Any]], bool]:
    per_file_best: list[DestinationScore] = []
    aggregate: dict[str, DestinationScore] = {}
    for feature in bundle.attachments:
        scores = _score_single_attachment(feature, runtime_text)
        best = scores[0]
        per_file_best.append(best)
        for item in scores:
            prev = aggregate.get(item.destination)
            if prev is None or item.score > prev.score:
                aggregate[item.destination] = item

    strong_destinations = {item.destination for item in per_file_best if item.score >= _THRESHOLD and item.destination not in {DEST_ASK, DEST_NONE}}
    if len(strong_destinations) >= 2:
        candidates = sorted((item.to_dict() for item in aggregate.values()), key=lambda d: d["score"], reverse=True)
        return DEST_ASK, 0.0, "MULTI_ATTACHMENT_CONFLICT", candidates, True

    candidates = sorted((item.to_dict() for item in aggregate.values()), key=lambda d: d["score"], reverse=True)
    if not candidates:
        return DEST_ASK, 0.0, "NO_ATTACHMENT_FEATURES", [], True
    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else {"score": 0.0}
    if float(best["score"]) < _THRESHOLD:
        return DEST_ASK, float(best["score"]), "LOW_CONFIDENCE_ATTACHMENT_FOLLOWUP", candidates, True
    if float(second.get("score", 0.0)) > 0 and float(best["score"]) - float(second["score"]) < _AMBIGUITY_DELTA:
        return DEST_ASK, float(best["score"]), "AMBIGUOUS_ATTACHMENT_FOLLOWUP", candidates, True
    return str(best["destination"]), float(best["score"]), str(best["reason_code"]), candidates, False


def policy_bootstrap_status(policy_ready_override: bool | None = None) -> PolicyBootstrapStatus:
    """Return whether box endpoints can pass the bootstrap gate.

    Production never calls target endpoints to compute this. It first tries the
    existing PolicyStore active-policy path. If that path is unavailable or fails,
    the result is fail-closed.
    """
    if policy_ready_override is not None:
        return PolicyBootstrapStatus(bool(policy_ready_override), POLICY_READY_METHOD_OVERRIDE, None if policy_ready_override else "POLICY_BOOTSTRAP_REQUIRED")
    try:
        from butler_pc_core.company_policy.storage import PolicyStore, PolicyLoadError  # type: ignore
    except Exception:
        return PolicyBootstrapStatus(False, POLICY_READY_METHOD_FAIL_CLOSED, "POLICY_BOOTSTRAP_STATUS_UNAVAILABLE")
    try:
        active = PolicyStore().load_active_policy()
    except Exception:
        return PolicyBootstrapStatus(False, POLICY_READY_METHOD_ACTIVE_POLICY, "POLICY_LOAD_FAILED")
    if active is None:
        return PolicyBootstrapStatus(False, POLICY_READY_METHOD_ACTIVE_POLICY, "POLICY_BOOTSTRAP_REQUIRED")
    return PolicyBootstrapStatus(True, POLICY_READY_METHOD_ACTIVE_POLICY, None)


def _load_company_fact_candidate_model() -> type[Any]:
    try:
        from butler_pc_core.company_fact.routes import CompanyFactCandidateRequest  # type: ignore
        return CompanyFactCandidateRequest
    except Exception as exc:
        raise CompanyFactSchemaUnavailable() from exc


def validate_company_fact_candidate_payload(payload: dict[str, Any], *, model_cls: type[Any] | None = None) -> str:
    """Validate structured candidate payload and return digest-only payload digest.

    This function intentionally does not build a payload from files. It only
    validates a payload already structured by a later document-to-candidate step.
    """
    model = model_cls or _load_company_fact_candidate_model()
    try:
        obj = model(**payload)
    except Exception as exc:
        raise IntakeContractError("INTAKE_COMPANY_FACT_CANDIDATE_SCHEMA_INVALID") from exc
    data = obj.model_dump() if hasattr(obj, "model_dump") else dict(getattr(obj, "__dict__", payload))
    confidence = float(data.get("confidence", payload.get("confidence", 0.5)))
    if confidence >= 1.0:
        raise IntakeContractError("INTAKE_CANDIDATE_CONFIDENCE_1_0_BLOCKED")
    if len(data.get("question_patterns", [])) < 2:
        raise IntakeContractError("INTAKE_CANDIDATE_QUESTION_PATTERNS_REQUIRED")
    if len(str(data.get("answer_runtime_text", ""))) < 10:
        raise IntakeContractError("INTAKE_CANDIDATE_ANSWER_TOO_SHORT")
    if len(str(data.get("source", ""))) < 3:
        raise IntakeContractError("INTAKE_CANDIDATE_SOURCE_REQUIRED")
    return stable_json_digest({"candidate_payload": data, "schema": "CompanyFactCandidateRequest"})


def _endpoint_for_destination(destination: str) -> tuple[str, str]:
    if destination in REAL_ENDPOINTS:
        return REAL_ENDPOINTS[destination]
    if destination in NON_CALLABLE_BOXES:
        box, _ = NON_CALLABLE_BOXES[destination]
        return box, "none"
    return "none", "none"


def _non_callable_fail(destination: str) -> str:
    return NON_CALLABLE_BOXES.get(destination, ("none", "ASK_FOLLOWUP"))[1]


def _decision_id_payload(*, request_id: str, bundle: AttachmentFeatureBundle, runtime_text: str | None, destination: str, candidate_payload_digest: str | None) -> dict[str, Any]:
    attachments = sorted(
        [
            {
                "file_digest": item["file_digest"],
                "file_kind": item["file_kind"],
                "feature_digest": item["feature_digest"],
                "extractor_fail_class": item.get("extractor_fail_class"),
            }
            for item in bundle.attachments
        ],
        key=lambda item: (item["file_digest"], item["feature_digest"]),
    )
    return {
        "schema_version": DECISION_ID_SCHEMA_VERSION,
        "request_id": request_id,
        "attachments": attachments,
        "runtime_text_digest": _runtime_digest(runtime_text),
        "primary_destination": destination,
        "feature_set_digest": bundle.feature_set_digest,
        "candidate_payload_digest": candidate_payload_digest,
    }


def _candidate_hint_for(destination: str) -> str | None:
    return CANDIDATE_ENDPOINT_HINT if destination == DEST_COMPANY_FACT else None


def _next_action_for_non_callable(destination: str) -> str:
    if destination == DEST_COMPANY_FACT:
        return "STRUCTURE_COMPANY_FACT_CANDIDATE_REQUIRED"
    if destination == DEST_COMPANY_FORMAT:
        return "ADMIN_FORMAT_REGISTRATION_REQUIRED"
    if destination == DEST_ASK:
        return "ASK_FOLLOWUP"
    if destination in {DEST_BOX4, DEST_BOX6, DEST_BOX7, DEST_BOX8}:
        return "ASK_FOLLOWUP"
    return "ASK_FOLLOWUP"


def _initial_decision(
    *,
    request_id: str,
    runtime_text: str | None,
    destination: str,
    target_box_id: str,
    target_endpoint: str,
    routing_confidence: float,
    reason_code: str,
    candidate_destinations: list[dict[str, Any]],
    bundle: AttachmentFeatureBundle,
    candidate_payload_ready: bool,
    candidate_payload_digest: str | None,
    policy_status: PolicyBootstrapStatus,
    fallback_required: bool,
    fail_class: str,
    next_action: str,
) -> dict[str, Any]:
    evidence = feature_summary_for_decision(bundle)
    decision_id = stable_json_digest(_decision_id_payload(
        request_id=request_id,
        bundle=bundle,
        runtime_text=runtime_text,
        destination=destination,
        candidate_payload_digest=candidate_payload_digest,
    ))
    decision = {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "decision_id": decision_id,
        "primary_destination": destination,
        "destination": destination,
        "target_box_id": target_box_id,
        "target_endpoint": target_endpoint,
        "candidate_endpoint_hint": _candidate_hint_for(destination),
        "candidate_payload_ready": candidate_payload_ready,
        "candidate_payload_digest": candidate_payload_digest,
        "policy_callable": bool(policy_status.ready),
        "policy_bootstrap": policy_status.to_dict(),
        "fallback_required": fallback_required,
        "fail_class": fail_class,
        "next_action": next_action,
        "routing_confidence": round(float(routing_confidence), 4),
        "reason_code": reason_code,
        "candidate_destinations": candidate_destinations,
        "feature_set_digest": bundle.feature_set_digest,
        "attachments": evidence["attachments"],
        "attachment_count": bundle.attachment_count,
        "attachment_evidence": evidence,
        "unsupported_files": evidence["unsupported_files"],
        "meta": {
            "feature_set_digest": bundle.feature_set_digest,
            "raw_text_logged": False,
            "sample_values_logged": False,
            "external_send_zero": True,
            "dispatcher_contract": "DISPATCH_TARGET_ENDPOINT_ONLY",
        },
        "raw_text_logged": False,
        "sample_values_logged": False,
        "external_send_zero": True,
    }
    assert_intake_payload_safe(decision)
    return decision


def decide_intake(
    *,
    request_id: str,
    attachment_bundle: AttachmentFeatureBundle,
    runtime_text: str | None = None,
    structured_candidate_payload: dict[str, Any] | None = None,
    policy_ready_override: bool | None = None,
    company_fact_model_cls: type[Any] | None = None,
) -> dict[str, Any]:
    destination, confidence, reason_code, candidates, ambiguous = _combine_scores(attachment_bundle, runtime_text)
    policy = policy_bootstrap_status(policy_ready_override)

    candidate_payload_ready = False
    candidate_payload_digest: str | None = None
    if destination == DEST_COMPANY_FACT and structured_candidate_payload is not None:
        try:
            candidate_payload_digest = validate_company_fact_candidate_payload(structured_candidate_payload, model_cls=company_fact_model_cls)
            candidate_payload_ready = True
        except IntakeContractError as exc:
            target_box, _ = _endpoint_for_destination(destination)
            return _initial_decision(
                request_id=request_id,
                runtime_text=runtime_text,
                destination=destination,
                target_box_id=target_box,
                target_endpoint="none",
                routing_confidence=confidence,
                reason_code=str(exc.fail_class),
                candidate_destinations=candidates,
                bundle=attachment_bundle,
                candidate_payload_ready=False,
                candidate_payload_digest=None,
                policy_status=policy,
                fallback_required=True,
                fail_class=str(exc.fail_class),
                next_action="BLOCK",
            )

    target_box, real_endpoint = _endpoint_for_destination(destination)

    if not policy.ready:
        return _initial_decision(
            request_id=request_id,
            runtime_text=runtime_text,
            destination=destination,
            target_box_id=target_box,
            target_endpoint="none",
            routing_confidence=confidence,
            reason_code=policy.fail_class or "POLICY_BOOTSTRAP_REQUIRED",
            candidate_destinations=candidates,
            bundle=attachment_bundle,
            candidate_payload_ready=candidate_payload_ready,
            candidate_payload_digest=candidate_payload_digest,
            policy_status=policy,
            fallback_required=True,
            fail_class=policy.fail_class or "POLICY_BOOTSTRAP_REQUIRED",
            next_action="POLICY_BOOTSTRAP_REQUIRED",
        )

    if destination == DEST_COMPANY_FACT and not candidate_payload_ready:
        return _initial_decision(
            request_id=request_id,
            runtime_text=runtime_text,
            destination=destination,
            target_box_id=target_box,
            target_endpoint="none",
            routing_confidence=confidence,
            reason_code="COMPANY_FACT_CANDIDATE_FILE_NEEDS_STRUCTURING",
            candidate_destinations=candidates,
            bundle=attachment_bundle,
            candidate_payload_ready=False,
            candidate_payload_digest=None,
            policy_status=policy,
            fallback_required=True,
            fail_class="INTAKE_CANDIDATE_PAYLOAD_NOT_READY",
            next_action="STRUCTURE_COMPANY_FACT_CANDIDATE_REQUIRED",
        )

    if destination in NON_CALLABLE_BOXES or destination == DEST_ASK or ambiguous:
        fail = reason_code if ambiguous else _non_callable_fail(destination)
        action = "ASK_FOLLOWUP" if destination not in {DEST_COMPANY_FORMAT, DEST_COMPANY_FACT} else _next_action_for_non_callable(destination)
        return _initial_decision(
            request_id=request_id,
            runtime_text=runtime_text,
            destination=destination,
            target_box_id=target_box,
            target_endpoint="none",
            routing_confidence=confidence,
            reason_code=reason_code,
            candidate_destinations=candidates,
            bundle=attachment_bundle,
            candidate_payload_ready=candidate_payload_ready,
            candidate_payload_digest=candidate_payload_digest,
            policy_status=policy,
            fallback_required=True,
            fail_class=fail,
            next_action=action,
        )

    if real_endpoint not in ALLOWED_TARGET_ENDPOINTS:
        raise IntakeContractError("INTAKE_TARGET_ENDPOINT_INVALID")
    return _initial_decision(
        request_id=request_id,
        runtime_text=runtime_text,
        destination=destination,
        target_box_id=target_box,
        target_endpoint=real_endpoint,
        routing_confidence=confidence,
        reason_code=reason_code,
        candidate_destinations=candidates,
        bundle=attachment_bundle,
        candidate_payload_ready=candidate_payload_ready,
        candidate_payload_digest=candidate_payload_digest,
        policy_status=policy,
        fallback_required=False,
        fail_class="",
        next_action="CALL_BOX_ENDPOINT",
    )


def dispatchable_endpoint(decision: dict[str, Any]) -> str | None:
    """Return the only field a dispatcher may use. Hints are intentionally ignored."""
    endpoint = decision.get("target_endpoint")
    if endpoint and endpoint != "none":
        return str(endpoint)
    return None


def _get_field(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def assert_intake_payload_safe(decision: dict[str, Any]) -> None:
    for field in INSPECTED_RAW_FIELDS:
        value = _get_field(decision, field)
        if isinstance(value, str) and _PATH_OR_FILENAME_RE.search(value):
            raise IntakeContractError("INTAKE_RAW_PATH_OR_FILENAME_LEAK")
    if decision.get("raw_text_logged") is not False:
        raise IntakeContractError("INTAKE_RAW_TEXT_LOGGED_NOT_FALSE")
    if decision.get("external_send_zero") is not True:
        raise IntakeContractError("INTAKE_EXTERNAL_SEND_ZERO_NOT_TRUE")
    meta = decision.get("meta")
    if not isinstance(meta, dict):
        raise IntakeContractError("INTAKE_META_MISSING")
    feature_set_digest = meta.get("feature_set_digest") or decision.get("feature_set_digest")
    if not isinstance(feature_set_digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", feature_set_digest):
        raise IntakeContractError("INTAKE_FEATURE_SET_DIGEST_MISSING")
    if meta.get("raw_text_logged") is not False:
        raise IntakeContractError("INTAKE_RAW_TEXT_LOGGED_NOT_FALSE")
    if meta.get("external_send_zero") is not True:
        raise IntakeContractError("INTAKE_EXTERNAL_SEND_ZERO_NOT_TRUE")
    if decision.get("target_endpoint") not in ALLOWED_TARGET_ENDPOINTS:
        raise IntakeContractError("INTAKE_TARGET_ENDPOINT_INVALID")
    # Canonical serialization smoke check. Do not substring-scan backslashes: JSON
    # escaping would false-positive valid decisions. Required raw-like field names
    # are already excluded by construction and field-aware inspection above.
    canonical_json(decision)
