from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Literal, Mapping


SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def validate_reason_code(value: str) -> None:
    if not REASON_CODE_RE.fullmatch(value):
        raise ValueError("MODEL_TIER_REASON_CODE_INVALID")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("MODEL_TIER_NON_STRING_JSON_KEY")
        return {key: _jsonable(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(child) for child in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_jsonable(child) for child in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("MODEL_TIER_VALUE_NOT_JSON_SERIALIZABLE")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def stable_digest(value: Any) -> str:
    return sha256_text(canonical_json(value))


class ModelTier(str, Enum):
    MODEL_NONE = "MODEL_NONE"
    TIER_1P7B = "TIER_1P7B"
    TIER_4B = "TIER_4B"


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"
    DISABLED = "DISABLED"


class ProfileValidity(str, Enum):
    VALID = "VALID"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


class MemoryPressure(str, Enum):
    NORMAL = "NORMAL"
    WARN = "WARN"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class ThermalState(str, Enum):
    NOMINAL = "NOMINAL"
    FAIR = "FAIR"
    SERIOUS = "SERIOUS"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RouteOverride:
    """Test-only decision input; production code must never construct this object."""

    test_only: Literal[True]
    requested_tier: ModelTier

    def validate(self) -> None:
        if self.test_only is not True:
            raise ValueError("ROUTE_OVERRIDE_PRODUCTION_FORBIDDEN")


@dataclass(frozen=True)
class ModelVariant:
    schema_version: str
    variant_id: str
    role: str
    family: str
    tier: ModelTier
    quantization: str
    path_env_key: str
    allowed_boxes: tuple[str, ...]
    embedded_adapters: tuple[str, ...] = ()
    external_helpers: tuple[str, ...] = ()
    supports_json_grammar: bool = False
    supports_chat_template: bool = True
    max_context_tokens: int | None = None
    sealed_model_digest: str | None = None
    availability: Availability = Availability.UNVERIFIED
    general_purpose: bool = False

    def validate(self) -> None:
        if self.schema_version != "butler.model_variant.v1":
            raise ValueError("MODEL_VARIANT_SCHEMA_INVALID")
        if not self.variant_id or not self.role or not self.family:
            raise ValueError("MODEL_VARIANT_IDENTITY_REQUIRED")
        if self.tier is ModelTier.MODEL_NONE:
            raise ValueError("MODEL_NONE_IS_NOT_A_VARIANT")
        if self.sealed_model_digest is not None and not is_sha256(self.sealed_model_digest):
            raise ValueError("MODEL_VARIANT_DIGEST_INVALID")
        if self.availability is Availability.AVAILABLE and self.sealed_model_digest is None:
            raise ValueError("AVAILABLE_MODEL_REQUIRES_SEALED_DIGEST")
        if self.max_context_tokens is not None and self.max_context_tokens <= 0:
            raise ValueError("MODEL_VARIANT_CONTEXT_INVALID")
        if self.availability is not Availability.DISABLED and not self.path_env_key:
            raise ValueError("MODEL_VARIANT_PATH_ENV_REQUIRED")
        if len(set(self.allowed_boxes)) != len(self.allowed_boxes):
            raise ValueError("MODEL_VARIANT_DUPLICATE_SCOPE")

    def persistable_dict(self) -> dict[str, Any]:
        self.validate()
        return _jsonable(self)


@dataclass(frozen=True)
class RuntimeVariantState:
    variant_id: str
    loaded: bool
    ready: bool
    model_digest: str | None
    model_path_digest: str | None
    process_id_digest: str | None = None
    asset_available: bool = False

    def validate(self) -> None:
        if not self.variant_id:
            raise ValueError("RUNTIME_VARIANT_ID_REQUIRED")
        for value in (self.model_digest, self.model_path_digest, self.process_id_digest):
            if value is not None and not is_sha256(value):
                raise ValueError("RUNTIME_VARIANT_DIGEST_INVALID")
        if self.ready and self.model_digest is None:
            raise ValueError("RUNTIME_READY_MODEL_DIGEST_REQUIRED")
        if self.ready and not self.loaded:
            raise ValueError("RUNTIME_READY_REQUIRES_LOADED")
        if self.loaded and not self.asset_available:
            raise ValueError("RUNTIME_LOADED_REQUIRES_ASSET")

    @property
    def resident(self) -> bool:
        return self.loaded and self.ready


@dataclass(frozen=True)
class DeviceProfile:
    schema_version: str
    platform: str
    architecture: str
    chip_family: str
    total_memory_bytes: int | None
    available_memory_bytes: int | None
    process_rss_bytes: int | None
    memory_pressure: MemoryPressure
    thermal_state: ThermalState
    low_power_mode: bool | None
    battery_percent: float | None
    metal_available: bool | None
    profiler_source: str
    collected_at_epoch_ms: int
    validity: ProfileValidity
    probe_errors: tuple[str, ...] = ()
    raw_text_logged: Literal[False] = False

    def validate(self) -> None:
        if self.schema_version != "butler.device_profile.v1":
            raise ValueError("DEVICE_PROFILE_SCHEMA_INVALID")
        if self.collected_at_epoch_ms < 0:
            raise ValueError("DEVICE_PROFILE_TIMESTAMP_INVALID")
        for value in (self.total_memory_bytes, self.available_memory_bytes, self.process_rss_bytes):
            if value is not None and (isinstance(value, bool) or value < 0):
                raise ValueError("DEVICE_PROFILE_MEMORY_INVALID")
        if self.total_memory_bytes == 0:
            raise ValueError("DEVICE_PROFILE_TOTAL_ZERO")
        if (
            self.total_memory_bytes is not None
            and self.available_memory_bytes is not None
            and self.available_memory_bytes > self.total_memory_bytes
        ):
            raise ValueError("DEVICE_PROFILE_AVAILABLE_EXCEEDS_TOTAL")
        if self.battery_percent is not None and not 0.0 <= self.battery_percent <= 100.0:
            raise ValueError("DEVICE_PROFILE_BATTERY_INVALID")
        if self.validity is ProfileValidity.VALID and (
            self.total_memory_bytes is None or self.available_memory_bytes is None
        ):
            raise ValueError("DEVICE_PROFILE_VALID_MEASUREMENTS_REQUIRED")
        for error in self.probe_errors:
            validate_reason_code(error)

    @property
    def profile_digest(self) -> str:
        self.validate()
        return stable_digest(self)

    def persistable_dict(self) -> dict[str, Any]:
        self.validate()
        return _jsonable(self)


@dataclass(frozen=True)
class TaskProfile:
    schema_version: str
    box_id: str
    task_class: str
    payload_digest: str
    input_chars: int
    attachment_count: int
    total_attachment_bytes: int
    estimated_input_tokens: int
    requested_output_tokens: int
    reference_count: int
    structured_output_required: bool
    deterministic_path_available: bool
    ambiguity_score: float
    quality_risk_flags: tuple[str, ...] = ()
    security_risk_flags: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.schema_version != "butler.task_profile.v1":
            raise ValueError("TASK_PROFILE_SCHEMA_INVALID")
        if self.box_id not in {"1", "3"}:
            raise ValueError("TASK_PROFILE_BOX_UNSUPPORTED")
        if not is_sha256(self.payload_digest):
            raise ValueError("TASK_PROFILE_DIGEST_INVALID")
        if not 0.0 <= self.ambiguity_score <= 1.0:
            raise ValueError("TASK_PROFILE_AMBIGUITY_INVALID")
        for value in (
            self.input_chars,
            self.attachment_count,
            self.total_attachment_bytes,
            self.estimated_input_tokens,
            self.requested_output_tokens,
            self.reference_count,
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError("TASK_PROFILE_COUNT_INVALID")
        for flag in (*self.quality_risk_flags, *self.security_risk_flags):
            validate_reason_code(flag)

    @property
    def task_digest(self) -> str:
        self.validate()
        return stable_digest(self)

    def persistable_dict(self) -> dict[str, Any]:
        self.validate()
        return _jsonable(self)


@dataclass(frozen=True)
class BoxPolicy:
    schema_version: str
    box_id: str
    enabled: bool
    shadow_only: Literal[True]
    default_variant_id: str | None
    allowed_variant_ids: tuple[str, ...]
    hard_block_reason_codes: frozenset[str]
    cascade_soft_reason_codes: frozenset[str]
    minimum_available_memory_bytes: dict[str, int] = field(default_factory=dict)
    max_escalations: Literal[1] = 1

    def validate(self) -> None:
        if self.schema_version != "butler.box_policy.v1":
            raise ValueError("BOX_POLICY_SCHEMA_INVALID")
        if self.box_id not in {"1", "3"}:
            raise ValueError("BOX_POLICY_SCOPE_INVALID")
        if self.shadow_only is not True or self.max_escalations != 1:
            raise ValueError("BOX_POLICY_PHASE0_INVARIANT_FAILED")
        if self.default_variant_id and self.default_variant_id not in self.allowed_variant_ids:
            raise ValueError("BOX_POLICY_DEFAULT_NOT_ALLOWED")
        if self.hard_block_reason_codes & self.cascade_soft_reason_codes:
            raise ValueError("BOX_POLICY_REASON_CLASS_OVERLAP")
        for reason in self.hard_block_reason_codes | self.cascade_soft_reason_codes:
            validate_reason_code(reason)
        for variant_id, required in self.minimum_available_memory_bytes.items():
            if variant_id not in self.allowed_variant_ids or required < 0:
                raise ValueError("BOX_POLICY_MEMORY_REQUIREMENT_INVALID")

    @property
    def policy_digest(self) -> str:
        self.validate()
        return stable_digest(self)


@dataclass(frozen=True)
class TierDecision:
    schema_version: str
    box_id: str
    recommended_tier: ModelTier
    recommended_variant_id: str | None
    eligible_variant_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    high_eligible: bool
    shadow_only: Literal[True]
    applied: Literal[False]
    task_digest: str
    device_profile_digest: str
    policy_digest: str
    decision_digest: str

    @classmethod
    def build(
        cls,
        *,
        box_id: str,
        recommended_tier: ModelTier,
        recommended_variant_id: str | None,
        eligible_variant_ids: tuple[str, ...],
        reason_codes: tuple[str, ...],
        high_eligible: bool,
        task_digest: str,
        device_profile_digest: str,
        policy_digest: str,
    ) -> "TierDecision":
        unsigned = {
            "schema_version": "butler.tier_decision.v1",
            "box_id": box_id,
            "recommended_tier": recommended_tier.value,
            "recommended_variant_id": recommended_variant_id,
            "eligible_variant_ids": list(eligible_variant_ids),
            "reason_codes": list(reason_codes),
            "high_eligible": high_eligible,
            "shadow_only": True,
            "applied": False,
            "task_digest": task_digest,
            "device_profile_digest": device_profile_digest,
            "policy_digest": policy_digest,
        }
        decision = cls(
            schema_version="butler.tier_decision.v1",
            box_id=box_id,
            recommended_tier=recommended_tier,
            recommended_variant_id=recommended_variant_id,
            eligible_variant_ids=eligible_variant_ids,
            reason_codes=reason_codes,
            high_eligible=high_eligible,
            shadow_only=True,
            applied=False,
            task_digest=task_digest,
            device_profile_digest=device_profile_digest,
            policy_digest=policy_digest,
            decision_digest=stable_digest(unsigned),
        )
        decision.validate()
        return decision

    def validate(self) -> None:
        if self.schema_version != "butler.tier_decision.v1":
            raise ValueError("TIER_DECISION_SCHEMA_INVALID")
        if self.box_id not in {"1", "3"}:
            raise ValueError("TIER_DECISION_BOX_INVALID")
        if self.shadow_only is not True or self.applied is not False:
            raise ValueError("TIER_DECISION_PHASE0_INVARIANT_FAILED")
        if self.recommended_tier is ModelTier.MODEL_NONE and self.recommended_variant_id is not None:
            raise ValueError("MODEL_NONE_VARIANT_MUST_BE_NULL")
        if self.recommended_variant_id and self.recommended_variant_id not in self.eligible_variant_ids:
            raise ValueError("TIER_DECISION_VARIANT_NOT_ELIGIBLE")
        for reason in self.reason_codes:
            validate_reason_code(reason)
        if not self.reason_codes:
            raise ValueError("TIER_DECISION_REASON_REQUIRED")
        for digest in (
            self.task_digest,
            self.device_profile_digest,
            self.policy_digest,
            self.decision_digest,
        ):
            if not is_sha256(digest):
                raise ValueError("TIER_DECISION_DIGEST_INVALID")

    def persistable_dict(self) -> dict[str, Any]:
        self.validate()
        return _jsonable(self)


@dataclass(frozen=True)
class GateResult:
    schema_version: str
    passed: bool
    reason_code: str | None
    severity: Literal["pass", "soft", "hard"]
    quality_vector: dict[str, float | int | bool]
    result_digest: str

    def validate(self) -> None:
        if self.schema_version != "butler.gate_result.v1":
            raise ValueError("GATE_RESULT_SCHEMA_INVALID")
        if self.reason_code:
            validate_reason_code(self.reason_code)
        if self.passed and self.severity != "pass":
            raise ValueError("GATE_RESULT_PASS_SEVERITY_INVALID")
        if not is_sha256(self.result_digest):
            raise ValueError("GATE_RESULT_DIGEST_INVALID")
        canonical_json(self.quality_vector)


@dataclass(frozen=True)
class CascadePlan:
    schema_version: str
    box_id: str
    would_escalate: bool
    escalation_allowed: bool
    reason_code: str
    required_runtime_inputs: tuple[str, ...]
    max_additional_model_calls: Literal[1]
    shadow_only: Literal[True]
    actual_model_invocations: Literal[0]
    plan_digest: str

    def validate(self) -> None:
        if self.schema_version != "butler.cascade_plan.v1" or self.box_id != "3":
            raise ValueError("CASCADE_PLAN_SCOPE_INVALID")
        if self.shadow_only is not True or self.actual_model_invocations != 0:
            raise ValueError("CASCADE_PLAN_PHASE0_INVARIANT_FAILED")
        if self.max_additional_model_calls != 1:
            raise ValueError("CASCADE_PLAN_CALL_LIMIT_INVALID")
        if self.escalation_allowed and not self.would_escalate:
            raise ValueError("CASCADE_PLAN_ALLOW_WITHOUT_INTENT")
        validate_reason_code(self.reason_code)
        if not is_sha256(self.plan_digest):
            raise ValueError("CASCADE_PLAN_DIGEST_INVALID")

    def persistable_dict(self) -> dict[str, Any]:
        self.validate()
        return _jsonable(self)
