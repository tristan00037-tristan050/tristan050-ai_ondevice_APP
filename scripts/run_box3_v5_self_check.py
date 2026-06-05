#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.cards.box3.v5_asset_manifest import build_v5_asset_manifest, manifest_allows_v5_real
from butler_pc_core.cards.box3.v5_activation_gate import V5EndpointMetricSnapshot, evaluate_v5_activation_gate
from butler_pc_core.cards.box3.v5_degeneration_gate import detect_v5_degeneration


def main() -> int:
    manifest = build_v5_asset_manifest().to_dict()
    degeneration = detect_v5_degeneration(
        "제목: 참고 문서 기반 초안\n배경: 참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다. (근거1)\n핵심 내용: 납품 일정은 2026년 6월 10일입니다. (근거1)\n근거: source_digest citation으로 확인합니다.\n확인 필요: 담당자와 금액은 [문서에 근거 없음]으로 표시합니다.\n최종 문안: 납품 일정은 2026년 6월 10일 기준으로 검토합니다. (근거1)"
    ).to_dict()
    metrics = V5EndpointMetricSnapshot(
        unsupported_count=0,
        supported_count=2,
        citation_accuracy=0.97,
        format_compliance=0.90,
        style_compliance=0.80,
        table_figure_coverage=1.0,
        degeneration_detected=degeneration["degeneration_detected"],
        abstain_ratio=0.2,
        section_completeness=0.9,
        raw_saved_zero=True,
        external_send_zero=True,
    )
    decision = evaluate_v5_activation_gate(
        asset_manifest=manifest,
        metrics=metrics,
        regression_passed=True,
        fixed_eval_passed=False,
        human_approval_allowed=False,
    ).to_dict()
    report = {
        "schema_version": "box3.v5.self_check.v1_2",
        "manifest_status": manifest["status"],
        "manifest_allows_real": manifest_allows_v5_real(manifest),
        "decision": decision,
        "degeneration": degeneration,
        "raw_saved_zero": True,
        "external_send_zero": True,
    }
    out_dir = ROOT / "evidence" / "box3_v5_activation"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "self_check_v1_2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
