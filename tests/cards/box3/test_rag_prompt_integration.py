from __future__ import annotations

from butler_pc_core.cards.box3.rag_prompt_integration import build_rag_grounded_prompt_runtime
from butler_pc_core.cards.box3.rag_context import RuntimeEvidenceUnit, sha256_text


class Envelope:
    request_id = "req-test"
    drafting_request_runtime_only = "납품 일정 근거로 초안 작성"
    reference_text_runtime_only = ["납품 일정은 2026년 6월 10일입니다."]
    max_new_tokens = 256

    @property
    def request_digest(self):
        return sha256_text(self.drafting_request_runtime_only)


class Bundle:
    def __init__(self):
        self.evidence_units_runtime = [
            RuntimeEvidenceUnit(
                evidence_id="e1",
                source_digest=sha256_text("source"),
                evidence_digest=sha256_text("납품 일정은 2026년 6월 10일입니다."),
                kind="text",
                text_runtime_only="납품 일정은 2026년 6월 10일입니다.",
            )
        ]


def test_integration_attaches_runtime_prompt_to_envelope():
    env = Envelope()
    result = build_rag_grounded_prompt_runtime(env, Bundle())
    assert result.grounded_prompt.evidence_marker_count == 1
    assert hasattr(env, "grounded_prompt_runtime_only")
    assert "각 사실 문장 끝" in env.grounded_prompt_runtime_only
    assert result.to_stage_trace_entry()["raw_saved_zero"] is True


def test_stage_trace_is_digest_only():
    env = Envelope()
    result = build_rag_grounded_prompt_runtime(env, Bundle())
    trace = result.to_stage_trace_entry()
    assert "prompt_digest" in trace
    assert "납품" not in str(trace)
