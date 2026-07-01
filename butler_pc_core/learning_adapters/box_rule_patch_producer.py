from __future__ import annotations

import dataclasses
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from butler_pc_core.learning_core.contracts import (
    IntegratedLearningError,
    assert_no_forbidden_fields,
    is_sha256,
    stable_json_digest,
)
from butler_pc_core.learning_core.runner import LearningIntakeRunner

PRODUCER_VERSION = "box_rule_patch_producer.v1.2.0"
SCHEMA_VERSION = "integrated_learning_candidate.v1"
TARGET_KIND = "box_rule_patch"
LEARNING_SOURCE_TYPE = "verified_box_rule_patch"
DEFAULT_VERIFIED_AT = "2026-07-01T00:00:00Z"
DIGEST_ONLY_EVIDENCE_REF = "digest-only-fixture"

_ALLOWED_SOURCE_REF_TYPES = frozenset({"usage_log", "approval", "folder", "format", "policy"})
_LOCAL_FORBIDDEN_ARTIFACT_FIELDS = frozenset(
    {
        "raw",
        "raw_text",
        "raw_memo",
        "transaction_text",
        "account_number_plain",
        "amount_plain",
        "prompt",
        "response_text",
        "md_content",
        "filename",
        "file_name",
        "file_path",
        "local_path",
        "full_diff",
        "full_diff_text",
        "diff_text",
        "rule_text",
        "customer_name",
        "holder_plain",
        "vendor_plain",
        "integration_mode",
    }
)
_SHA_HEX_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


class BoxRulePatchProducerError(ValueError):
    """Fail-closed error for malformed producer input.

    The message is a stable drop code so callers can return digest-safe summaries
    without serialising the rejected artifact.
    """


@dataclass(frozen=True)
class Box5RulePatchArtifact:
    """Digest/ref-only artifact from a verified Box5 rule-base evaluation.

    This is not a runtime patch and not PEFT/model training input. It is a narrow
    producer-side value object that can be converted into
    integrated_learning_candidate.v1 and then passed through
    LearningIntakeRunner.ingest().
    """

    rule_target: str
    changed_files: tuple[str, ...]
    tests_to_run: tuple[str, ...]
    expected_current_digest: str
    rule_tokens_digest: str
    fixed_eval_report_digest: str
    expected_effect_digest: str
    group_a_fixed_eval_passed: bool = True
    runtime_hotpatch: bool = False
    proposed_diff_digest: str | None = None
    approved_rule_token_digest: str | None = None
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)
    verified_by: str = "group_a"
    verified_at: str = DEFAULT_VERIFIED_AT
    evidence_digest: str | None = None


def _fail(code: str) -> None:
    raise BoxRulePatchProducerError(code)


def _stable_digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha_hex(value: str) -> str:
    match = _SHA_HEX_RE.fullmatch(value)
    if not match:
        _fail("DIGEST_INVALID")
    return match.group(1)


def _ensure_no_forbidden_keys(value: Any) -> None:
    try:
        assert_no_forbidden_fields(value)
    except IntegratedLearningError as exc:
        _fail(str(exc))

    def walk(node: Any, path: str = "$") -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                if key in _LOCAL_FORBIDDEN_ARTIFACT_FIELDS:
                    _fail(f"FORBIDDEN_FIELD:{path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for index, child in enumerate(node):
                walk(child, f"{path}[{index}]")
        elif isinstance(node, str):
            # Producer/queue outputs should not carry local refs or full refs. Only
            # digest-only-fixture and sha256 strings are allowed to leave this layer.
            if "vault://" in node or "keyring://" in node:
                _fail(f"REF_MATERIAL_FORBIDDEN:{path}")

    walk(value)


def _tuple_of_str(values: Sequence[str] | tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        _fail(f"{field_name}_REQUIRED")
    cleaned = tuple(str(item).strip() for item in values if str(item or "").strip())
    if not cleaned:
        _fail(f"{field_name}_REQUIRED")
    return cleaned


def _bool_field(data: Mapping[str, Any], field_name: str, *, default: bool, error_code: str) -> bool:
    if field_name not in data:
        return default
    value = data[field_name]
    if not isinstance(value, bool):
        _fail(error_code)
    return value


def _source_refs_from_mapping(data: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    raw = data.get("source_refs", ())
    if raw is None:
        return ()
    if isinstance(raw, Mapping) or not isinstance(raw, (list, tuple)):
        _fail("SOURCE_REFS_NOT_SEQUENCE")
    refs: list[dict[str, str]] = []
    for ref in raw:
        if not isinstance(ref, Mapping):
            _fail("SOURCE_REF_NOT_OBJECT")
        refs.append(dict(ref))
    return tuple(refs)


def _validate_digest_or_drop(value: str | None, field_name: str, *, required: bool = True) -> str | None:
    if value is None:
        if required:
            _fail(f"{field_name}_DIGEST_REQUIRED")
        return None
    if not is_sha256(value):
        _fail(f"{field_name}_DIGEST_INVALID")
    return value


def _normalize_source_refs(source_refs: Sequence[Mapping[str, str]] | None, fallback_digest: str) -> tuple[dict[str, str], ...]:
    if not source_refs:
        return ({"ref_type": "approval", "ref_id_digest": fallback_digest},)
    normalized: list[dict[str, str]] = []
    for ref in source_refs:
        if not isinstance(ref, Mapping):
            _fail("SOURCE_REF_NOT_OBJECT")
        ref_type = str(ref.get("ref_type", "")).strip()
        ref_id_digest = str(ref.get("ref_id_digest", "")).strip()
        if ref_type not in _ALLOWED_SOURCE_REF_TYPES:
            _fail("SOURCE_REF_TYPE_INVALID")
        if not is_sha256(ref_id_digest):
            _fail("SOURCE_REF_DIGEST_INVALID")
        normalized.append({"ref_type": ref_type, "ref_id_digest": ref_id_digest})
    return tuple(normalized)


def coerce_box5_rule_patch_artifact(artifact: Box5RulePatchArtifact | Mapping[str, Any]) -> Box5RulePatchArtifact:
    """Accept a typed artifact or a mapping and fail closed on unknown/raw fields."""

    if isinstance(artifact, Box5RulePatchArtifact):
        data = dataclasses.asdict(artifact)
    elif isinstance(artifact, Mapping):
        data = dict(artifact)
    else:
        _fail("ARTIFACT_NOT_OBJECT")

    _ensure_no_forbidden_keys(data)
    allowed = {field.name for field in dataclasses.fields(Box5RulePatchArtifact)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail(f"ARTIFACT_UNKNOWN_FIELD:{unknown[0]}")

    try:
        return Box5RulePatchArtifact(
            rule_target=str(data["rule_target"]).strip(),
            changed_files=_tuple_of_str(data["changed_files"], "CHANGED_FILES"),
            tests_to_run=_tuple_of_str(data["tests_to_run"], "TESTS_TO_RUN"),
            expected_current_digest=str(data["expected_current_digest"]).strip(),
            rule_tokens_digest=str(data["rule_tokens_digest"]).strip(),
            fixed_eval_report_digest=str(data["fixed_eval_report_digest"]).strip(),
            expected_effect_digest=str(data["expected_effect_digest"]).strip(),
            group_a_fixed_eval_passed=_bool_field(
                data,
                "group_a_fixed_eval_passed",
                default=True,
                error_code="GROUP_A_FIXED_EVAL_PASSED_INVALID",
            ),
            runtime_hotpatch=_bool_field(
                data,
                "runtime_hotpatch",
                default=False,
                error_code="RUNTIME_HOTPATCH_INVALID",
            ),
            proposed_diff_digest=(None if data.get("proposed_diff_digest") is None else str(data.get("proposed_diff_digest")).strip()),
            approved_rule_token_digest=(
                None if data.get("approved_rule_token_digest") is None else str(data.get("approved_rule_token_digest")).strip()
            ),
            source_refs=_source_refs_from_mapping(data),
            verified_by=str(data.get("verified_by", "group_a")).strip() or "group_a",
            verified_at=str(data.get("verified_at", DEFAULT_VERIFIED_AT)).strip(),
            evidence_digest=(None if data.get("evidence_digest") is None else str(data.get("evidence_digest")).strip()),
        )
    except KeyError as exc:
        _fail(f"ARTIFACT_FIELD_REQUIRED:{exc.args[0]}")


def build_box_rule_patch_candidate(artifact: Box5RulePatchArtifact | Mapping[str, Any]) -> dict[str, Any]:
    """Convert a verified Box5 rule patch artifact to integrated_learning_candidate.v1.

    The candidate is digest-only, always receives a new stable `ilc-` id, and is
    intentionally not a verified_rule_base_candidate.v1 object.
    """

    item = coerce_box5_rule_patch_artifact(artifact)
    _validate_digest_or_drop(item.rule_tokens_digest, "RULE_TOKENS")
    _validate_digest_or_drop(item.fixed_eval_report_digest, "FIXED_EVAL_REPORT")
    _validate_digest_or_drop(item.expected_effect_digest, "EXPECTED_EFFECT")
    evidence_digest = _validate_digest_or_drop(item.evidence_digest or item.fixed_eval_report_digest, "EVIDENCE")
    approved_rule_token_digest = _validate_digest_or_drop(
        item.approved_rule_token_digest or item.rule_tokens_digest,
        "APPROVED_RULE_TOKEN",
    )
    # expected_current/proposed diff are adapter-verified so negative cases can
    # surface EXPECTED_CURRENT_DIGEST_INVALID / PROPOSED_DIFF_DIGEST_INVALID via
    # the normal runner path.
    source_refs = _normalize_source_refs(item.source_refs, approved_rule_token_digest)

    payload = {
        "rule_target": item.rule_target,
        "group_a_fixed_eval_passed": item.group_a_fixed_eval_passed,
        "runtime_hotpatch": item.runtime_hotpatch,
        "changed_files": list(item.changed_files),
        "tests_to_run": list(item.tests_to_run),
        "expected_current_digest": item.expected_current_digest,
        "proposed_diff_digest": item.proposed_diff_digest,
        "rule_tokens_digest": item.rule_tokens_digest,
        "fixed_eval_report_digest": item.fixed_eval_report_digest,
        "approved_rule_token_digest": approved_rule_token_digest,
    }
    payload_digest = stable_json_digest(payload)
    candidate_material = {
        "payload_digest": payload_digest,
        "expected_effect_digest": item.expected_effect_digest,
        "source_refs": list(source_refs),
        "evidence_digest": evidence_digest,
    }
    candidate_id = "ilc-" + _sha_hex(stable_json_digest(candidate_material))[:32]
    candidate = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "target_kind": TARGET_KIND,
        "adapter_version": PRODUCER_VERSION,
        "learning_source_type": LEARNING_SOURCE_TYPE,
        "policy_decision": "allow",
        "verified": True,
        "group_a_verified": True,
        "raw_text_logged": False,
        "external_send_zero": True,
        "model_training": False,
        "peft_training": False,
        "human_review_required": True,
        "auto_apply_to_runtime": False,
        "retention_class": "audit_digest_only",
        "verification": {
            "verified_by": item.verified_by,
            "verified_at": item.verified_at,
            "evidence_digest": evidence_digest,
            "evidence_ref": DIGEST_ONLY_EVIDENCE_REF,
        },
        "source_refs": list(source_refs),
        "payload_digest": payload_digest,
        "expected_effect_digest": item.expected_effect_digest,
        "payload": payload,
    }
    _ensure_no_forbidden_keys(candidate)
    return candidate


def box5_artifact_from_verified_rule_base_candidate(
    candidate: Mapping[str, Any],
    *,
    changed_files: Sequence[str],
    tests_to_run: Sequence[str],
    expected_current_digest: str,
    rule_tokens_digest: str,
) -> Box5RulePatchArtifact:
    """Compatibility bridge from verified_rule_base_candidate.v1 to A-adapter artifact.

    The incoming vrb-* candidate id is deliberately ignored; callers get a new
    stable ilc-* id when build_box_rule_patch_candidate() is called.
    """

    _ensure_no_forbidden_keys(candidate)
    if candidate.get("schema_version") != "verified_rule_base_candidate.v1":
        _fail("VRB_SCHEMA_VERSION_INVALID")
    if str(candidate.get("candidate_id", "")).startswith("ilc-"):
        _fail("VRB_CANDIDATE_ID_UNEXPECTED_ILC")
    if candidate.get("candidate_kind") != "deterministic_rule_patch":
        _fail("VRB_CANDIDATE_KIND_INVALID")
    if candidate.get("target") != "box5_self_transfer_guard":
        _fail("VRB_TARGET_INVALID")
    if candidate.get("group_a_verified") is not True:
        _fail("VRB_GROUP_A_NOT_VERIFIED")
    runtime_hotpatch = candidate.get("runtime_hotpatch", False)
    if not isinstance(runtime_hotpatch, bool):
        _fail("RUNTIME_HOTPATCH_INVALID")
    source_refs: list[dict[str, str]] = []
    for source_id in candidate.get("source_usage_log_ids", []) or []:
        text = str(source_id).strip()
        digest = text if is_sha256(text) else _stable_digest_text("usage_log:" + text)
        source_refs.append({"ref_type": "usage_log", "ref_id_digest": digest})
    if not source_refs:
        source_refs.append({"ref_type": "approval", "ref_id_digest": str(candidate.get("approved_rule_token_digest"))})
    return Box5RulePatchArtifact(
        rule_target="box5_self_transfer_guard",
        changed_files=_tuple_of_str(changed_files, "CHANGED_FILES"),
        tests_to_run=_tuple_of_str(tests_to_run, "TESTS_TO_RUN"),
        expected_current_digest=expected_current_digest,
        rule_tokens_digest=rule_tokens_digest,
        fixed_eval_report_digest=str(candidate.get("group_a_report_digest", "")).strip(),
        expected_effect_digest=str(candidate.get("expected_effect_digest", "")).strip(),
        proposed_diff_digest=candidate.get("proposed_diff_digest"),
        approved_rule_token_digest=str(candidate.get("approved_rule_token_digest", "")).strip(),
        group_a_fixed_eval_passed=bool(candidate.get("group_a_verified")),
        runtime_hotpatch=runtime_hotpatch,
        source_refs=tuple(source_refs),
        evidence_digest=str(candidate.get("group_a_report_digest", "")).strip(),
    )


def ingest_verified_box5_rule_patch(
    artifact: Box5RulePatchArtifact | Mapping[str, Any],
    runner: LearningIntakeRunner,
) -> dict[str, Any]:
    """Build candidate, call runner.ingest(), and return a digest-safe summary."""

    try:
        candidate = build_box_rule_patch_candidate(artifact)
    except BoxRulePatchProducerError as exc:
        return {
            "accepted": False,
            "drop_reason": str(exc),
            "queue_appended": False,
            "candidate_id": None,
            "target_kind": TARGET_KIND,
            "rule_target": None,
            "payload_digest": None,
            "record_digest": None,
        }
    result = runner.ingest(candidate)
    return {
        "accepted": bool(result.get("accepted")),
        "drop_reason": result.get("drop_reason"),
        "queue_appended": bool(result.get("queue_appended")),
        "queue_reason": result.get("queue_reason"),
        "candidate_id": candidate["candidate_id"],
        "target_kind": candidate["target_kind"],
        "rule_target": candidate["payload"]["rule_target"],
        "payload_digest": candidate["payload_digest"],
        "record_digest": result.get("record_digest"),
    }
