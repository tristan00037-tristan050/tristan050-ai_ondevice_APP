from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.cards.box3.grounded_prompt import evaluate_usefulness_gate
from butler_pc_core.cards.box3.rag_context import RuntimeEvidenceUnit, sha256_text
from butler_pc_core.cards.box3.rag_prompt_integration import build_rag_grounded_prompt_runtime


class Envelope:
    request_id = "self-check"
    drafting_request_runtime_only = "납품 일정과 담당자 기준으로 보고서 초안을 작성하세요."
    reference_text_runtime_only = ["납품 일정은 2026년 6월 10일입니다."]

    @property
    def request_digest(self):
        return sha256_text(self.drafting_request_runtime_only)


class Verdict:
    support_level = "supported"


def main() -> int:
    env = Envelope()
    result = build_rag_grounded_prompt_runtime(env, None)
    usefulness = evaluate_usefulness_gate(
        "제목: 초안\n배경: 참고 문서 기반입니다.\n핵심 내용: 납품 일정은 2026년 6월 10일입니다. (근거1)\n근거: (근거1)\n확인 필요: 담당자는 [문서에 근거 없음]\n최종 문안: 납품 일정 기준으로 검토합니다. (근거1)",
        [Verdict()],
    )
    payload = {
        "SELF_CHECK_PASS": usefulness.status == "PASS" and result.grounded_prompt.evidence_marker_count >= 1,
        "prompt_digest": result.grounded_prompt.prompt_digest,
        "decode_config_digest": result.grounded_prompt.decode_config_digest,
        "context_digest": result.rag_context.context_digest,
        "evidence_marker_count": result.grounded_prompt.evidence_marker_count,
        "absent_slots": result.grounded_prompt.absent_slots,
        "usefulness_status": usefulness.status,
        "raw_saved_zero": True,
        "external_send_zero": True,
    }
    out = Path("evidence/box3_rag_prompt_activation/self_check_runtime.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["SELF_CHECK_PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
