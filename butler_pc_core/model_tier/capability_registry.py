from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import Availability, ModelTier, ModelVariant, RuntimeVariantState


# Physical GGUF SHA-256 values measured from the canonical baseline bundle at
# origin/main 3b442f93. These are deliberately not model-path digests.
MAIN_QWEN3_4B_MODEL_DIGEST = (
    "sha256:1ce4b49ad9438433b504f427a58d1750e53f79fd780a741a2132b623ec234ffb"
)
BOX3_V9_2_R2B_MODEL_DIGEST = (
    "sha256:aae4ea7a4ebe0586db3317d5209b5565abcd326ea73decb7ffa99f433c218847"
)

MAIN_4B_VARIANT_ID = "main_qwen3_4b_q4_k_m"
BOX3_1P7B_VARIANT_ID = "box3_v9_2_r2b_1p7_q4_k_m"
BOX2_1P7B_VARIANT_ID = "box2_v3_1p7_q4_k_m"
BOX5_4B_PEFT_VARIANT_ID = "box5_qwen3_4b_accounting_peft"
GENERIC_1P7B_FUTURE_VARIANT_ID = "generic_1p7_fast_future"


@dataclass(frozen=True)
class CapabilityRegistry:
    variants: dict[str, ModelVariant]

    @classmethod
    def from_variants(cls, variants: Iterable[ModelVariant]) -> "CapabilityRegistry":
        values: dict[str, ModelVariant] = {}
        for variant in variants:
            variant.validate()
            if variant.variant_id in values:
                raise ValueError("DUPLICATE_MODEL_VARIANT_ID")
            values[variant.variant_id] = variant
        return cls(values)

    def get_variant(self, variant_id: str) -> ModelVariant:
        try:
            return self.variants[variant_id]
        except KeyError as exc:
            raise KeyError("MODEL_VARIANT_NOT_REGISTERED") from exc

    def eligible_for_scope(
        self,
        scope: str,
        runtime_states: dict[str, RuntimeVariantState],
    ) -> tuple[ModelVariant, ...]:
        eligible: list[ModelVariant] = []
        for variant in self.variants.values():
            state = runtime_states.get(variant.variant_id)
            if scope not in variant.allowed_boxes:
                continue
            if variant.availability is not Availability.AVAILABLE:
                continue
            if state is None:
                continue
            try:
                state.validate()
            except ValueError:
                continue
            if not state.ready:
                continue
            if variant.sealed_model_digest != state.model_digest:
                continue
            eligible.append(variant)
        return tuple(sorted(eligible, key=lambda item: item.variant_id))


def phase0_default_registry() -> CapabilityRegistry:
    return CapabilityRegistry.from_variants(
        [
            ModelVariant(
                schema_version="butler.model_variant.v1",
                variant_id=MAIN_4B_VARIANT_ID,
                role="general_office_chat_box4_box6_box3_repair",
                family="qwen3-4b",
                tier=ModelTier.TIER_4B,
                quantization="Q4_K_M",
                path_env_key="BUTLER_MODEL_PATH",
                allowed_boxes=("1", "3-repair", "4", "6", "chat"),
                supports_json_grammar=True,
                supports_chat_template=True,
                max_context_tokens=32_768,
                sealed_model_digest=MAIN_QWEN3_4B_MODEL_DIGEST,
                availability=Availability.AVAILABLE,
                general_purpose=True,
            ),
            ModelVariant(
                schema_version="butler.model_variant.v1",
                variant_id=BOX3_1P7B_VARIANT_ID,
                role="box3_specialized_draft_generator",
                family="butler-1.7b-v9.2-r2b",
                tier=ModelTier.TIER_1P7B,
                quantization="Q4_K_M",
                path_env_key="BUTLER_BOX3_V9_Q4_MODEL_PATH",
                allowed_boxes=("3",),
                embedded_adapters=("helper3_format", "helper5_tool_call"),
                external_helpers=(
                    "helper4_grounding",
                    "helper7_evidence",
                    "helper8_company_style",
                ),
                supports_chat_template=True,
                max_context_tokens=8_192,
                sealed_model_digest=BOX3_V9_2_R2B_MODEL_DIGEST,
                availability=Availability.AVAILABLE,
                general_purpose=False,
            ),
            ModelVariant(
                schema_version="butler.model_variant.v1",
                variant_id=BOX2_1P7B_VARIANT_ID,
                role="box2_inventory_only",
                family="butler-v3-1.7b",
                tier=ModelTier.TIER_1P7B,
                quantization="Q4_K_M",
                path_env_key="BUTLER_BOX2_MODEL_PATH",
                allowed_boxes=("2",),
                embedded_adapters=("helper3_rewrite",),
                availability=Availability.UNVERIFIED,
                general_purpose=False,
            ),
            ModelVariant(
                schema_version="butler.model_variant.v1",
                variant_id=BOX5_4B_PEFT_VARIANT_ID,
                role="box5_accounting_opt_in",
                family="qwen3-4b-peft",
                tier=ModelTier.TIER_4B,
                quantization="FP16_PEFT",
                path_env_key="ACCOUNTING_PEFT_ADAPTER_PATH",
                allowed_boxes=("5",),
                embedded_adapters=("accounting_classifier",),
                availability=Availability.UNVERIFIED,
                general_purpose=False,
            ),
            ModelVariant(
                schema_version="butler.model_variant.v1",
                variant_id=GENERIC_1P7B_FUTURE_VARIANT_ID,
                role="generic_fast_candidate",
                family="unassigned",
                tier=ModelTier.TIER_1P7B,
                quantization="UNASSIGNED",
                path_env_key="",
                allowed_boxes=(),
                availability=Availability.DISABLED,
                general_purpose=True,
            ),
        ]
    )
