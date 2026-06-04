"""박스 3 helper3/5 LoRA fusion 진단 실측 스크립트 (PR #782, 2026-06-05).

PR #781 머지본(acf0148f) 위에서 ALG ``lora_fusion`` SSOT 4 축 진단을 base
``butler-1.7b-v4-rt-q4_k_m.gguf`` 에 대해 1회 실행한다.

4 evidence axes:
  1) lineage_build  — 모델 디렉터리 안 release/build manifest 흔적
  2) gguf_metadata  — GGUF 파일 metadata 의 provenance / lora / merge / adapter 흔적
  3) runner_code    — ``local_sealed_runner`` 실제 LoRA load/apply/merge 호출 흔적
  4) behavior_probe — base-only 추론에서 helper3 (format) / helper5 (tool_call) 능력
                      manifest 여부 (LoRA 미적용 상태)

판정 기준 (ALG ``diagnose_helper35_fusion``):
  - 최소 3 축이 already_fused 일치 + core 충돌 없음 → A) ALREADY_FUSED_CONFIRMED
    → action=DO_NOT_FUSE_REPORT_MODEL_LIMIT (재학습 / qwen3-4b 교체 보고)
  - 최소 3 축이 not_fused 일치 + core 충돌 없음 → B) NOT_FUSED_CONFIRMED
    → action=FUSION_ALLOWED_RUNTIME_LORA_OR_MERGE_GGUF
  - 그 외 → C) INCONCLUSIVE → action=FUSION_FORBIDDEN_REMEASURE (fusion 0)

정직 출력 정책: raw output text / 절대 경로 / prompt 텍스트 0. 모든 영구 라벨은
digest / 카운트 / 라벨만.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from butler_pc_core.cards.box3.lora_fusion.diagnosis import (
    FusionEvidenceAxis,
    diagnose_helper35_fusion,
)
from butler_pc_core.cards.box3.lora_fusion.security import sha256_text

BASE_GGUF_PATH = Path(
    "/Users/kimsunghoon/Desktop/butler-data/학습모델/"
    "butler-1.7b-v4-rt/butler-1.7b-v4-rt/butler-1.7b-v4-rt-q4_k_m.gguf"
)
EXPECTED_BASE_SHA = "60b9baee17696ca8e3a3aa0950a4d441ad3c4baa80bbd73ec9fa33c17cba0c1f"


def _axis_lineage_build() -> dict:
    """Axis 1: 모델 산출물 트리에서 build/release manifest 흔적 스캔 (raw 0)."""
    parent = BASE_GGUF_PATH.parent.parent
    fused_kw = ("merged", "merge_to_gguf", "lora_fused", "post-merge", "merge_and_unload")
    not_fused_kw = ("base only", "no lora", "without lora", "pre-fusion")
    fused_hits, not_fused_hits = 0, 0
    file_count = 0
    for f in parent.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in {".json", ".md", ".txt", ".yaml", ".yml"}:
            continue
        if f.stat().st_size > 200_000:
            continue
        file_count += 1
        try:
            t = f.read_text(encoding="utf-8", errors="ignore").casefold()
        except Exception:
            continue
        for kw in fused_kw:
            if kw in t:
                fused_hits += 1
        for kw in not_fused_kw:
            if kw in t:
                not_fused_hits += 1
    if fused_hits > not_fused_hits and fused_hits > 0:
        verdict, conf = "already_fused", 0.65
    elif not_fused_hits > fused_hits and not_fused_hits > 0:
        verdict, conf = "not_fused", 0.65
    else:
        verdict, conf = "inconclusive", 0.30
    counters = {"file_count": file_count, "fused_hits": fused_hits, "not_fused_hits": not_fused_hits}
    evidence_digest = sha256_text(json.dumps({"axis": "lineage_build", **counters}, sort_keys=True))
    return {"axis": "lineage_build", "verdict": verdict, "confidence": conf, "evidence_digest": evidence_digest, "counters": counters}


def _axis_gguf_metadata() -> dict:
    """Axis 2: GGUF metadata provenance 검사 — 'merged' / lora / adapter 흔적."""
    from llama_cpp import Llama

    llm = Llama(model_path=str(BASE_GGUF_PATH), n_ctx=256, verbose=False)
    meta = dict(llm.metadata)
    del llm
    lora_keys = [k for k in meta if "lora" in k.casefold() or "adapter" in k.casefold()]
    name_lower = str(meta.get("general.name", "")).casefold()
    finetune_lower = str(meta.get("general.finetune", "")).casefold()
    basename_lower = str(meta.get("general.basename", "")).casefold()
    has_merged_label = (
        "merged" in name_lower
        or "merged" in finetune_lower
        or "merged" in basename_lower
        or "fused" in name_lower
        or "fused" in finetune_lower
    )
    # explicit lora key in metadata is a stronger signal than name labels alone.
    if lora_keys:
        verdict, conf = "already_fused", 0.85
    elif has_merged_label:
        # name says merged but no helper3/5 specific lora key — moderate confidence.
        verdict, conf = "already_fused", 0.65
    else:
        verdict, conf = "inconclusive", 0.40
    counters = {
        "total_metadata_key_count": len(meta),
        "lora_or_adapter_key_count": len(lora_keys),
        "has_merged_label": has_merged_label,
        "general_name_digest": sha256_text(name_lower),
        "general_finetune_digest": sha256_text(finetune_lower),
    }
    evidence_digest = sha256_text(json.dumps({"axis": "gguf_metadata", **counters}, sort_keys=True))
    return {"axis": "gguf_metadata", "verdict": verdict, "confidence": conf, "evidence_digest": evidence_digest, "counters": counters}


def _axis_runner_code() -> dict:
    """Axis 3: runner 코드의 실제 LoRA load / apply / merge 호출 흔적."""
    runner = REPO_ROOT / "butler_pc_core" / "cards" / "box3" / "local_sealed_runner.py"
    text = runner.read_text(encoding="utf-8")
    direct_lora_call = bool(
        re.search(
            r"lora_path\s*=|apply_lora|merge_lora|load_lora|set_lora_adapter|"
            r"PeftModel|adapter_name|loras\s*=",
            text,
        )
    )
    declared_only = "declared_by_local_probe" in text
    if direct_lora_call:
        # runner is actually applying LoRA at runtime → NOT_FUSED (would not need
        # to apply at runtime if already fused into base GGUF).
        verdict, conf = "not_fused", 0.85
    elif declared_only:
        # runner only declares stack; doesn't apply. This is consistent with either
        # ALREADY_FUSED (no runtime apply needed) or NOT_FUSED (capability missing).
        verdict, conf = "inconclusive", 0.55
    else:
        verdict, conf = "inconclusive", 0.30
    counters = {
        "direct_lora_call_detected": direct_lora_call,
        "declared_only_marker": declared_only,
        "runner_path_digest": sha256_text("ref:butler_pc_core/cards/box3/local_sealed_runner.py"),
    }
    evidence_digest = sha256_text(json.dumps({"axis": "runner_code", **counters}, sort_keys=True))
    return {"axis": "runner_code", "verdict": verdict, "confidence": conf, "evidence_digest": evidence_digest, "counters": counters}


def _axis_behavior_probe() -> dict:
    """Axis 4: base-only 추론에서 helper3/5 능력 manifest 여부 (raw 0).

    LoRA 가 runtime 에 적용되지 않으므로, helper3 (한국어 6단 보고서 format)
    및 helper5 (JSON tool_call shape) 능력이 base 추론에서 나타난다면
    GGUF 가 이미 fused; 아니라면 not_fused 강한 시사.
    """
    from llama_cpp import Llama

    llm = Llama(model_path=str(BASE_GGUF_PATH), n_ctx=2048, verbose=False)

    probe_format = (
        "다음 사용자 요청에 한국어 6단 보고서 (제목/배경/핵심 내용/근거/확인 필요/최종 문안) "
        "형식으로 답하세요.\n사용자 요청: 납품 일정 확인 보고서 초안 작성\n"
    )
    r1 = llm(probe_format, max_tokens=140, temperature=0.0, stop=["</s>", "<|im_end|>"])
    out1 = (r1["choices"][0]["text"] or "").strip()
    sections_present = sum(
        1 for s in ("제목", "배경", "핵심", "근거", "확인", "최종") if s in out1
    )

    probe_tool = (
        "다음 사용자 요청에 JSON 형식의 tool call 만 출력하세요. 예: "
        "{\"tool\": \"send_email\", \"args\": {\"to\": \"...\"}}\n"
        "사용자 요청: 김부장에게 회의 알림 메일 보내기\n"
    )
    r2 = llm(probe_tool, max_tokens=100, temperature=0.0, stop=["</s>", "<|im_end|>"])
    out2 = (r2["choices"][0]["text"] or "").strip()
    json_shape = (
        "{" in out2 and "}" in out2 and ("tool" in out2.casefold() or '"args"' in out2)
    )
    del llm

    # Decision rule (digest-only): helper3+helper5 capability manifest threshold.
    if sections_present >= 4 and json_shape:
        verdict, conf = "already_fused", 0.85
    elif sections_present <= 2 and not json_shape:
        verdict, conf = "not_fused", 0.85
    else:
        verdict, conf = "inconclusive", 0.55

    out1_digest = "sha256:" + hashlib.sha256(out1.encode("utf-8")).hexdigest()
    out2_digest = "sha256:" + hashlib.sha256(out2.encode("utf-8")).hexdigest()
    counters = {
        "helper3_sections_present_count": sections_present,
        "helper3_sections_total": 6,
        "helper5_json_shape_detected": json_shape,
        "probe_format_output_digest": out1_digest,
        "probe_tool_output_digest": out2_digest,
    }
    evidence_digest = sha256_text(json.dumps({"axis": "behavior_probe", **counters}, sort_keys=True))
    return {"axis": "behavior_probe", "verdict": verdict, "confidence": conf, "evidence_digest": evidence_digest, "counters": counters}


def main() -> int:
    base_sha_actual = hashlib.sha256(BASE_GGUF_PATH.read_bytes()).hexdigest()
    base_sha_match = base_sha_actual == EXPECTED_BASE_SHA

    axes_raw = [_axis_lineage_build(), _axis_gguf_metadata(), _axis_runner_code(), _axis_behavior_probe()]
    axes = [
        FusionEvidenceAxis(
            axis=a["axis"],  # type: ignore[arg-type]
            verdict=a["verdict"],  # type: ignore[arg-type]
            evidence_digest=a["evidence_digest"],
            confidence=a["confidence"],
            evidence_ref=f"ref:diagnosis_v1_2.{a['axis']}",
        )
        for a in axes_raw
    ]

    verdict = diagnose_helper35_fusion(axes, attempted_stack_helpers=["helper3_format", "helper5_tool_call"])
    verdict_payload = verdict.to_dict()

    code_letter = {
        "ALREADY_FUSED_CONFIRMED": "A",
        "NOT_FUSED_CONFIRMED": "B",
        "INCONCLUSIVE": "C",
        "BLOCKED": "BLOCKED",
    }.get(verdict.diagnosis_status, "?")

    report = {
        "schema_version": "box3.helper35_lora_fusion.smoke.v1_2",
        "base_artifact": {
            "name_ref": "ref:butler-1.7b-v4-rt-q4_k_m.gguf",
            "expected_sha256_full": EXPECTED_BASE_SHA,
            "sha256_match": base_sha_match,
        },
        "evidence_axes": [
            {
                "axis": a["axis"],
                "verdict": a["verdict"],
                "confidence": a["confidence"],
                "evidence_digest": a["evidence_digest"],
                "counters": a["counters"],
            }
            for a in axes_raw
        ],
        "diagnosis_verdict": verdict_payload,
        "diagnosis_code_letter": code_letter,
        "fusion_allowed": verdict.fusion_allowed,
        "next_action": verdict.action,
        "raw_saved_zero": True,
        "external_send_zero": True,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
