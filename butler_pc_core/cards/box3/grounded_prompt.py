from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .actual_contracts import assert_persistable_digest_only, sha256_text, stable_json_digest
from .actual_fail_class import NEEDS_REVIEW_UNSUPPORTED_CLAIM
from .rag_prompt_integration import RAGContextPacket, build_rag_context_packet

ABSTAINED_SLOT_TEXT = "[근거 부족: 확인 필요]"
_REQUIRED_SECTIONS = ["제목", "배경", "핵심 내용", "근거", "확인 필요", "최종 문안"]


@dataclass(frozen=True)
class DecodeConfig:
    temperature: float = 0.2
    top_p: float = 0.9
    max_new_tokens: int = 512
    no_external_send: bool = True

    @property
    def digest(self) -> str:
        return stable_json_digest(asdict(self))


@dataclass(frozen=True)
class FewshotExample:
    fewshot_id: str
    source_digest: str
    prompt_digest: str
    response_digest: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class FewshotPack:
    schema_version: str
    examples: list[FewshotExample]
    pack_digest: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "examples": [example.to_dict() for example in self.examples],
            "pack_digest": self.pack_digest,
        }
        assert_persistable_digest_only(payload)
        return payload


@dataclass(frozen=True)
class GroundedPromptPacket:
    schema_version: str
    prompt_runtime_only: str
    prompt_digest: str
    decode_config_digest: str
    context_digest: str
    evidence_marker_count: int
    absent_slots: list[str]
    fewshot_ids: list[str]
    external_send_zero: bool = True
    raw_saved_zero: bool = True

    def to_persistable_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "prompt_digest": self.prompt_digest,
            "decode_config_digest": self.decode_config_digest,
            "context_digest": self.context_digest,
            "evidence_marker_count": self.evidence_marker_count,
            "absent_slots": list(self.absent_slots),
            "fewshot_ids": list(self.fewshot_ids),
            "external_send_zero": True,
            "raw_saved_zero": True,
        }
        assert_persistable_digest_only(payload)
        return payload

    def to_stage_trace_entry(self) -> dict[str, Any]:
        return {
            "stage": "grounded_prompt",
            "context_digest": self.context_digest,
            "prompt_digest": self.prompt_digest,
            "evidence_marker_count": self.evidence_marker_count,
            "absent_slot_count": len(self.absent_slots),
        }


def _default_fewshot_pack() -> FewshotPack:
    # Digest-only examples; runtime prompt includes only short synthetic, non-user text.
    examples = [
        FewshotExample(
            fewshot_id="box3_grounded_positive_v1",
            source_digest=sha256_text("synthetic: supported evidence"),
            prompt_digest=sha256_text("근거에 있는 수치만 작성"),
            response_digest=sha256_text("지원되는 초안"),
        ),
        FewshotExample(
            fewshot_id="box3_grounded_abstain_v1",
            source_digest=sha256_text("synthetic: missing evidence"),
            prompt_digest=sha256_text("근거가 없으면 확인 필요"),
            response_digest=sha256_text(ABSTAINED_SLOT_TEXT),
        ),
    ]
    pack_digest = stable_json_digest([example.to_dict() for example in examples])
    return FewshotPack("box3.fewshot_pack.v1_1", examples, pack_digest)


def _render_evidence_cards(context: RAGContextPacket) -> str:
    lines = []
    for marker in context.selected_evidence_markers:
        lines.append(f"- [{marker.marker_id}] digest={marker.evidence_digest} kind={marker.kind}")
    if not lines:
        return "- 사용 가능한 근거 없음"
    return "\n".join(lines)


def build_grounded_prompt_packet(
    envelope: Any,
    rag_context: RAGContextPacket,
    *,
    decode_config: DecodeConfig | None = None,
    fewshot_pack: FewshotPack | None = None,
) -> GroundedPromptPacket:
    decode_config = decode_config or DecodeConfig(max_new_tokens=int(getattr(envelope, "max_new_tokens", 512)))
    fewshot_pack = fewshot_pack or _default_fewshot_pack()
    user_intent_digest = sha256_text(str(getattr(envelope, "drafting_request_runtime_only", "")))
    format_hint_digest = sha256_text(str(getattr(envelope, "format_hint", "")))

    prompt = (
        "시스템: 당신은 Butler Box3 초안 생성 엔진입니다. 외부 전송 없이 로컬 근거만 사용합니다.\n"
        "규칙:\n"
        "1. 아래 [근거 카드]에 없는 사실·수치·날짜·담당자를 새로 만들지 마십시오.\n"
        f"2. 근거가 부족한 항목은 반드시 '{ABSTAINED_SLOT_TEXT}'로 남기십시오.\n"
        "3. 제목/배경/핵심 내용/근거/확인 필요/최종 문안 섹션을 유지하십시오.\n"
        "4. 인용은 digest 라벨만 사용하고 원문을 재출력하지 마십시오.\n\n"
        f"요청 digest: {user_intent_digest}\n"
        f"형식 hint digest: {format_hint_digest}\n"
        f"fewshot_pack: {fewshot_pack.pack_digest}\n\n"
        "[근거 카드]\n"
        f"{_render_evidence_cards(rag_context)}\n\n"
        "[초안 작성]\n"
        "제목:\n배경:\n핵심 내용:\n근거:\n확인 필요:\n최종 문안:\n"
    )
    packet = GroundedPromptPacket(
        schema_version="box3.grounded_prompt.v1_1",
        prompt_runtime_only=prompt,
        prompt_digest=sha256_text(prompt),
        decode_config_digest=decode_config.digest,
        context_digest=rag_context.context_digest,
        evidence_marker_count=len(rag_context.selected_evidence_markers),
        absent_slots=list(rag_context.absent_slots),
        fewshot_ids=[example.fewshot_id for example in fewshot_pack.examples],
    )
    packet.to_persistable_dict()
    return packet


@dataclass(frozen=True)
class UsefulnessGateResult:
    status: Literal["PASS", "PARTIAL", "BLOCK"]
    fail_class: str | None
    supported_claim_count: int
    factual_claim_count: int
    section_completeness: float
    abstain_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _section_completeness(draft_text: str) -> float:
    if not draft_text.strip():
        return 0.0
    return sum(1 for section in _REQUIRED_SECTIONS if f"{section}:" in draft_text) / len(_REQUIRED_SECTIONS)


def _abstain_ratio(draft_text: str) -> float:
    section_count = max(1, len(_REQUIRED_SECTIONS))
    return draft_text.count(ABSTAINED_SLOT_TEXT) / section_count


def evaluate_usefulness_gate(
    draft_text: str,
    claim_verdicts: list[Any],
    *,
    min_supported_claim_count: int = 1,
    min_section_completeness: float = 0.67,
    max_abstain_ratio: float = 0.60,
) -> UsefulnessGateResult:
    factual = [v for v in claim_verdicts if getattr(v, "support_level", None) != "non_claim"]
    supported = [v for v in factual if getattr(v, "support_level", None) == "supported"]
    unsupported = [v for v in factual if getattr(v, "support_level", None) == "unsupported"]

    completeness = _section_completeness(draft_text)
    abstain_ratio = _abstain_ratio(draft_text)

    if unsupported:
        return UsefulnessGateResult("PARTIAL", NEEDS_REVIEW_UNSUPPORTED_CLAIM, len(supported), len(factual), completeness, abstain_ratio)
    if len(supported) < min_supported_claim_count:
        return UsefulnessGateResult("PARTIAL", "PARTIAL_SUPPORTED_CLAIM_COUNT_LOW", len(supported), len(factual), completeness, abstain_ratio)
    if completeness < min_section_completeness:
        return UsefulnessGateResult("PARTIAL", "PARTIAL_SECTION_COMPLETENESS_LOW", len(supported), len(factual), completeness, abstain_ratio)
    if abstain_ratio > max_abstain_ratio:
        return UsefulnessGateResult("PARTIAL", "PARTIAL_ABSTAIN_OVERUSE", len(supported), len(factual), completeness, abstain_ratio)
    return UsefulnessGateResult("PASS", None, len(supported), len(factual), completeness, abstain_ratio)


def prepare_grounded_prompt_for_envelope(
    envelope: Any,
    evidence_bundle: Any,
    *,
    max_context_chars: int = 6000,
    top_k: int = 8,
    decode_config: DecodeConfig | None = None,
) -> tuple[RAGContextPacket, GroundedPromptPacket]:
    rag_context = build_rag_context_packet(envelope, evidence_bundle, max_context_chars=max_context_chars, top_k=top_k)
    grounded_prompt = build_grounded_prompt_packet(envelope, rag_context, decode_config=decode_config)
    # dataclass is not slotted in the current main; attach runtime-only attributes.
    setattr(envelope, "rag_context_runtime_only", rag_context)
    setattr(envelope, "grounded_prompt_runtime_only", grounded_prompt.prompt_runtime_only)
    setattr(envelope, "grounded_prompt_packet", grounded_prompt)
    return rag_context, grounded_prompt

# === PR-B: Citation Bridge — endpoint evidence → v9.1 학습형 [근거 카드] ===
def _extract_copy_value(text: str) -> str:
    if ":" in text:
        return text.split(":", 1)[1].strip()
    return text.strip()
