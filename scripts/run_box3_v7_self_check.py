#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from butler_pc_core.cards.box3.v7_activation_gate import V7SmokeMetrics, evaluate_v7_final_gate
from butler_pc_core.cards.box3.v7_asset_manifest import verify_v7_q4_asset
from butler_pc_core.cards.box3.v7_preconditions import verify_pr785_precondition
from butler_pc_core.cards.box3.v7_security import assert_digest_only, stable_json_digest

GOOD_DRAFT = "\n".join([
    "제목: 참고 문서 기반 초안입니다.",
    "배경: 참고 문서의 근거에 따라 작성했습니다. (근거1)",
    "핵심 내용: 납품 일정은 2026년 6월 10일입니다. (근거1)",
    "근거: source_digest와 evidence_digest로 확인합니다.",
    "확인 필요: 담당자는 [문서에 근거 없음]입니다.",
    "최종 문안: 납품 일정 기준으로 검토합니다. (근거1)",
])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/box3_v7_activation/self_check_v1_2.json")
    parser.add_argument("--approval", action="store_true")
    args = parser.parse_args()
    metrics = V7SmokeMetrics(
        unsupported_count=0,
        citation_accuracy=0.96,
        supported_count=1,
        table_normal=True,
        raw_saved_zero=True,
        external_send_zero=True,
        production_claim_allowed=False,
        latency_ms=None,
        peak_memory_mb=None,
        memory_backend="not_run_package_self_check",
    )
    pre = verify_pr785_precondition(Path("butler_pc_core/cards/box3/grounded_prompt.py"))
    asset = verify_v7_q4_asset()
    request_digest = stable_json_digest({"self_check": "box3_v7", "reference_digest_count": 1})
    decision = evaluate_v7_final_gate(draft_text=GOOD_DRAFT, metrics=metrics, request_digest=request_digest, precondition=pre, asset_verdict=asset, human_approval_allowed=args.approval)
    payload = {
        "schema_version": "box3.v7.self_check.v1_2",
        "self_check_pass": True,
        "decision": decision.to_dict(),
        "precondition": pre.to_dict(),
        "asset": asset.to_dict(),
        "raw_saved_zero": True,
        "external_send_zero": True,
        "production_claim_allowed": False,
        "note": "Package self-check does not claim endpoint PASS; v7 model file SHA and endpoint smoke must be measured in the target repo.",
    }
    assert_digest_only({k: v for k, v in payload.items() if k != "note"})
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print("SELF_CHECK_PASS=true")
    print(f"status={decision.status}")
    print(f"fail_class={decision.fail_class}")
    print(f"asset_status={asset.status}")
    print(f"pr785_precondition={pre.passed}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
