from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .grounded_prompt import DecodeConfig, GroundedPromptPacket, prepare_grounded_prompt_for_envelope
from .rag_context import RAGContextPacket, assert_persistable_digest_only


@dataclass(frozen=True)
class Box3RagPromptIntegrationResult:
    rag_context: RAGContextPacket
    grounded_prompt: GroundedPromptPacket

    def to_stage_trace_entry(self) -> dict[str, Any]:
        payload = {
            "stage": "rag_grounded_prompt",
            "passed": self.grounded_prompt.evidence_marker_count >= 1,
            "prompt_digest": self.grounded_prompt.prompt_digest,
            "decode_config_digest": self.grounded_prompt.decode_config_digest,
            "context_digest": self.rag_context.context_digest,
            "evidence_marker_count": self.grounded_prompt.evidence_marker_count,
            "absent_slot_count": len(self.grounded_prompt.absent_slots),
            "truncation_reason": self.rag_context.token_budget.get("truncation_reason"),
            "raw_saved_zero": True,
        }
        assert_persistable_digest_only(payload)
        return payload


def build_rag_grounded_prompt_runtime(
    envelope: Any,
    evidence_bundle: Any,
    *,
    max_context_chars: int = 6000,
    top_k: int = 8,
    decode_config: DecodeConfig | None = None,
) -> Box3RagPromptIntegrationResult:
    rag_context, grounded_prompt = prepare_grounded_prompt_for_envelope(
        envelope,
        evidence_bundle,
        max_context_chars=max_context_chars,
        top_k=top_k,
        decode_config=decode_config,
    )
    return Box3RagPromptIntegrationResult(rag_context=rag_context, grounded_prompt=grounded_prompt)
