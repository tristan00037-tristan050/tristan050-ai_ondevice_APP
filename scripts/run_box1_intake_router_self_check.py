from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.connect_loop.attachment_features import RuntimeAttachment, extract_attachment_features
from butler_pc_core.connect_loop.intake_router import decide_intake, dispatchable_endpoint


class FakeCompanyFactCandidateRequest:
    def __init__(self, **data):
        if len(data.get("question_patterns", [])) < 2:
            raise ValueError("question_patterns")
        if len(data.get("answer_runtime_text", "")) < 10:
            raise ValueError("answer")
        if len(data.get("source", "")) < 3:
            raise ValueError("source")
        if float(data.get("confidence", 0.5)) >= 1.0:
            raise ValueError("confidence")
        self._data = dict(data)
    def model_dump(self):
        return dict(self._data)


def _bundle(text: str, filename: str, content_type: str):
    return extract_attachment_features([RuntimeAttachment(text.encode("utf-8"), filename=filename, content_type=content_type)])


def main() -> None:
    bank = decide_intake(
        request_id="self-check-bank",
        attachment_bundle=_bundle("거래일자,입금,출금,잔액,적요\n2026-01-01,1000,0,1000,테스트", "bank.csv", "text/csv"),
        runtime_text="분개",
        policy_ready_override=True,
    )
    policy_file = decide_intake(
        request_id="self-check-policy-file",
        attachment_bundle=_bundle("제1조 목적. 회사 내규와 시행일 및 결재 절차", "policy.txt", "text/plain"),
        runtime_text="회사 규정",
        policy_ready_override=True,
    )
    structured = decide_intake(
        request_id="self-check-structured",
        attachment_bundle=_bundle("제1조 목적. 회사 내규와 시행일 및 결재 절차", "policy.txt", "text/plain"),
        runtime_text="회사 규정",
        structured_candidate_payload={
            "category": "company_policy",
            "question_patterns": ["연차 규정은?", "휴가 규정 알려줘"],
            "answer_runtime_text": "연차 승인 절차는 관리자 검토 후 확정됩니다.",
            "source": "사내규정",
            "confidence": 0.5,
        },
        policy_ready_override=True,
        company_fact_model_cls=FakeCompanyFactCandidateRequest,
    )
    policy_off = decide_intake(
        request_id="self-check-policy-off",
        attachment_bundle=_bundle("거래일자,입금,출금,잔액\n", "bank.csv", "text/csv"),
        runtime_text="분개",
        policy_ready_override=False,
    )
    report = {
        "schema_version": "box1.intake_router.self_check.v3_6",
        "bank_endpoint": bank["target_endpoint"],
        "bank_dispatchable": dispatchable_endpoint(bank),
        "file_company_fact_target_endpoint": policy_file["target_endpoint"],
        "file_company_fact_hint": policy_file["candidate_endpoint_hint"],
        "file_company_fact_policy_callable": policy_file["policy_callable"],
        "structured_candidate_endpoint": structured["target_endpoint"],
        "structured_candidate_payload_digest_present": bool(structured["candidate_payload_digest"]),
        "policy_off_target_endpoint": policy_off["target_endpoint"],
        "policy_off_fail_class": policy_off["fail_class"],
        "hint_non_dispatchable": dispatchable_endpoint(policy_file) is None,
        "pass": (
            bank["target_endpoint"] == "POST /accounting/classify"
            and policy_file["target_endpoint"] == "none"
            and policy_file["candidate_endpoint_hint"] == "POST /v1/company-facts/candidates"
            and structured["target_endpoint"] == "POST /v1/company-facts/candidates"
            and policy_off["target_endpoint"] == "none"
            and policy_off["fail_class"] == "POLICY_BOOTSTRAP_REQUIRED"
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
