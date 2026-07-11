from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from butler_pc_core.model_tier.box_policies import phase0_box1_policy, phase0_box3_policy
from butler_pc_core.model_tier.capability_registry import (
    BOX3_1P7B_VARIANT_ID,
    BOX3_V9_2_R2B_MODEL_DIGEST,
    MAIN_4B_VARIANT_ID,
    MAIN_QWEN3_4B_MODEL_DIGEST,
    phase0_default_registry,
)
from butler_pc_core.model_tier.cascade_policy import plan_shadow_cascade
from butler_pc_core.model_tier.contracts import (
    DeviceProfile,
    GateResult,
    MemoryPressure,
    ModelTier,
    ProfileValidity,
    RouteOverride,
    RuntimeVariantState,
    ThermalState,
    sha256_text,
    stable_digest,
)
from butler_pc_core.model_tier.task_profiler import classify_task_complexity
from butler_pc_core.model_tier.tier_router import route_tier


def _device() -> DeviceProfile:
    return DeviceProfile(
        schema_version="butler.device_profile.v1",
        platform="darwin",
        architecture="arm64",
        chip_family="Apple M3 Max",
        total_memory_bytes=64 * 1024**3,
        available_memory_bytes=24 * 1024**3,
        process_rss_bytes=4 * 1024**3,
        memory_pressure=MemoryPressure.NORMAL,
        thermal_state=ThermalState.NOMINAL,
        low_power_mode=False,
        battery_percent=80.0,
        metal_available=True,
        profiler_source="test",
        collected_at_epoch_ms=1,
        validity=ProfileValidity.VALID,
    )


def _states() -> dict[str, RuntimeVariantState]:
    return {
        MAIN_4B_VARIANT_ID: RuntimeVariantState(
            variant_id=MAIN_4B_VARIANT_ID,
            loaded=True,
            ready=True,
            model_digest=MAIN_QWEN3_4B_MODEL_DIGEST,
            model_path_digest=sha256_text("/models/main.gguf"),
        ),
        BOX3_1P7B_VARIANT_ID: RuntimeVariantState(
            variant_id=BOX3_1P7B_VARIANT_ID,
            loaded=True,
            ready=True,
            model_digest=BOX3_V9_2_R2B_MODEL_DIGEST,
            model_path_digest=sha256_text("/models/box3.gguf"),
        ),
    }


def _task(box_id: str, **overrides):
    facts = {
        "input_chars": 5000,
        "attachment_count": 1 if box_id == "3" else 0,
        "total_attachment_bytes": 4096 if box_id == "3" else 0,
        "requested_output_tokens": 1024,
        "reference_count": 1 if box_id == "3" else 0,
        "structured_output_required": False,
        "deterministic_path_available": False,
        "ambiguity_score": 0.7,
    }
    facts.update(overrides)
    return classify_task_complexity(box_id, facts)


def _gate(reason: str, severity: str) -> GateResult:
    unsigned = {
        "passed": False,
        "reason_code": reason,
        "severity": severity,
        "quality_vector": {},
    }
    return GateResult(
        schema_version="butler.gate_result.v1",
        passed=False,
        reason_code=reason,
        severity=severity,  # type: ignore[arg-type]
        quality_vector={},
        result_digest=stable_digest(unsigned),
    )


def test_registry_uses_physical_file_digests_not_path_digests() -> None:
    registry = phase0_default_registry()
    assert registry.get_variant(MAIN_4B_VARIANT_ID).sealed_model_digest == MAIN_QWEN3_4B_MODEL_DIGEST
    assert registry.get_variant(BOX3_1P7B_VARIANT_ID).sealed_model_digest == BOX3_V9_2_R2B_MODEL_DIGEST
    assert MAIN_QWEN3_4B_MODEL_DIGEST != sha256_text(
        "/Applications/Butler.app/Contents/Resources/models/qwen3-4b-q4_k_m.gguf"
    )


def test_box1_deterministic_request_recommends_no_model_even_when_4b_ready() -> None:
    decision = route_tier(
        task=_task("1", deterministic_path_available=True, ambiguity_score=0.1),
        device=_device(),
        policy=phase0_box1_policy(),
        registry=phase0_default_registry(),
        runtime_states=_states(),
    )
    assert decision.recommended_tier is ModelTier.MODEL_NONE
    assert decision.recommended_variant_id is None
    assert decision.shadow_only is True
    assert decision.applied is False


def test_box3_primary_is_specialized_1p7b_and_4b_is_repair_only() -> None:
    decision = route_tier(
        task=_task("3"),
        device=_device(),
        policy=phase0_box3_policy(),
        registry=phase0_default_registry(),
        runtime_states=_states(),
    )
    assert decision.recommended_variant_id == BOX3_1P7B_VARIANT_ID
    assert decision.recommended_tier is ModelTier.TIER_1P7B
    assert decision.high_eligible is True


def test_force_environment_presence_is_audited_but_never_applied() -> None:
    normal = route_tier(
        task=_task("3"),
        device=_device(),
        policy=phase0_box3_policy(),
        registry=phase0_default_registry(),
        runtime_states=_states(),
    )
    forced = route_tier(
        task=_task("3"),
        device=_device(),
        policy=phase0_box3_policy(),
        registry=phase0_default_registry(),
        runtime_states=_states(),
        route_override=RouteOverride(test_only=True, requested_tier=ModelTier.TIER_4B),
    )
    assert forced.recommended_variant_id == normal.recommended_variant_id
    assert "FORCE_ENV_IGNORED" in forced.reason_codes
    assert forced.applied is False


def test_soft_allowlist_can_recommend_exactly_one_future_call_without_execution() -> None:
    plan = plan_shadow_cascade(
        box_id="3",
        gate=_gate("NEEDS_REVIEW_CONTENT_DRIFT", "soft"),
        policy=phase0_box3_policy(),
        high_eligible=True,
    )
    assert plan.would_escalate is True
    assert plan.escalation_allowed is True
    assert plan.max_additional_model_calls == 1
    assert plan.actual_model_invocations == 0


@pytest.mark.parametrize("reason", ["BLOCK_DLP_OUTBOUND_DRAFT", "UNREGISTERED_NEW_FAILURE"])
def test_hard_or_unknown_reason_never_escalates(reason: str) -> None:
    plan = plan_shadow_cascade(
        box_id="3",
        gate=_gate(reason, "hard"),
        policy=phase0_box3_policy(),
        high_eligible=True,
    )
    assert plan.would_escalate is False
    assert plan.escalation_allowed is False
    assert plan.actual_model_invocations == 0


def test_unknown_device_profile_cannot_be_disguised_as_zero_memory() -> None:
    with pytest.raises(ValueError, match="DEVICE_PROFILE_TOTAL_ZERO"):
        replace(_device(), total_memory_bytes=0).validate()


def test_task_profiler_rejects_raw_fields() -> None:
    with pytest.raises(ValueError, match="RAW_FIELD_FORBIDDEN"):
        classify_task_complexity("1", {"text": "secret"})
