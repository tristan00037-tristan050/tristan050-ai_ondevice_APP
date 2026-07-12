from __future__ import annotations

from .capability_registry import (
    BOX3_1P7B_VARIANT_ID,
    MAIN_4B_VARIANT_ID,
    CapabilityRegistry,
)
from .contracts import (
    BoxPolicy,
    DeviceProfile,
    MemoryPressure,
    ModelTier,
    ProfileValidity,
    RouteOverride,
    RuntimeVariantState,
    TaskProfile,
    ThermalState,
    TierDecision,
)


def _memory_ok(variant_id: str, device: DeviceProfile, policy: BoxPolicy) -> bool:
    required = int(policy.minimum_available_memory_bytes.get(variant_id, 0))
    if required <= 0:
        return True
    return (
        device.validity is ProfileValidity.VALID
        and device.available_memory_bytes is not None
        and device.available_memory_bytes >= required
    )


def _high_resource_eligible(device: DeviceProfile) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if device.validity is not ProfileValidity.VALID:
        reasons.append("DEVICE_PROFILE_UNKNOWN")
    if device.memory_pressure in {MemoryPressure.WARN, MemoryPressure.CRITICAL}:
        reasons.append("DEVICE_MEMORY_PRESSURE")
    if device.thermal_state in {ThermalState.SERIOUS, ThermalState.CRITICAL}:
        reasons.append("DEVICE_THERMAL_PRESSURE")
    if device.low_power_mode is True:
        reasons.append("DEVICE_LOW_POWER_MODE")
    if device.battery_percent is not None and device.battery_percent < 20.0:
        reasons.append("DEVICE_BATTERY_LOW")
    if device.metal_available is False:
        reasons.append("DEVICE_METAL_UNAVAILABLE")
    return not reasons, tuple(reasons)


def route_tier(
    *,
    task: TaskProfile,
    device: DeviceProfile,
    policy: BoxPolicy,
    registry: CapabilityRegistry,
    runtime_states: dict[str, RuntimeVariantState],
    route_override: RouteOverride | None = None,
) -> TierDecision:
    task.validate()
    device.validate()
    policy.validate()
    if task.box_id != policy.box_id:
        raise ValueError("BOX_POLICY_SCOPE_MISMATCH")
    if not policy.enabled:
        return TierDecision.build(
            box_id=task.box_id,
            recommended_tier=ModelTier.MODEL_NONE,
            recommended_variant_id=None,
            eligible_variant_ids=(),
            reason_codes=("BOX_POLICY_DISABLED",),
            high_eligible=False,
            task_digest=task.task_digest,
            device_profile_digest=device.profile_digest,
            policy_digest=policy.policy_digest,
        )

    primary_scope = task.box_id
    primary = [
        variant
        for variant in registry.eligible_for_scope(primary_scope, runtime_states)
        if variant.variant_id in policy.allowed_variant_ids
        and _memory_ok(variant.variant_id, device, policy)
    ]
    repair = []
    if task.box_id == "3":
        repair = [
            variant
            for variant in registry.eligible_for_scope("3-repair", runtime_states)
            if variant.variant_id in policy.allowed_variant_ids
            and _memory_ok(variant.variant_id, device, policy)
        ]
    variants = {variant.variant_id: variant for variant in (*primary, *repair)}
    eligible_ids = tuple(sorted(variants))
    high_resource_ok, resource_reasons = _high_resource_eligible(device)
    reasons: list[str] = []
    if route_override is not None:
        route_override.validate()
        reasons.append("FORCE_ENV_IGNORED")
    reasons.extend(resource_reasons)
    if task.security_risk_flags:
        reasons.append("SECURITY_RISK_REQUIRES_EXISTING_PATH")

    selected_variant_id: str | None = None
    selected_tier = ModelTier.MODEL_NONE
    if task.box_id == "1":
        if task.deterministic_path_available and task.ambiguity_score < 0.25:
            reasons.append("BOX1_DETERMINISTIC_PATH_SUFFICIENT")
        elif MAIN_4B_VARIANT_ID in variants and high_resource_ok and not task.security_risk_flags:
            selected_variant_id = MAIN_4B_VARIANT_ID
            selected_tier = ModelTier.TIER_4B
            reasons.append("BOX1_COMPLEXITY_RECOMMENDS_CURRENT_4B")
        else:
            reasons.append("BOX1_NO_ELIGIBLE_MODEL")
    elif BOX3_1P7B_VARIANT_ID in variants:
        selected_variant_id = BOX3_1P7B_VARIANT_ID
        selected_tier = ModelTier.TIER_1P7B
        reasons.append("BOX3_SPECIALIZED_1P7B_PRIMARY")
    else:
        reasons.append("BOX3_PRIMARY_NOT_READY")

    high_eligible = bool(
        task.box_id == "3"
        and MAIN_4B_VARIANT_ID in variants
        and high_resource_ok
        and not task.security_risk_flags
    )
    if task.box_id == "3" and not high_eligible:
        reasons.append("BOX3_REPAIR_4B_NOT_ELIGIBLE")

    return TierDecision.build(
        box_id=task.box_id,
        recommended_tier=selected_tier,
        recommended_variant_id=selected_variant_id,
        eligible_variant_ids=eligible_ids,
        reason_codes=tuple(dict.fromkeys(reasons)),
        high_eligible=high_eligible,
        task_digest=task.task_digest,
        device_profile_digest=device.profile_digest,
        policy_digest=policy.policy_digest,
    )
