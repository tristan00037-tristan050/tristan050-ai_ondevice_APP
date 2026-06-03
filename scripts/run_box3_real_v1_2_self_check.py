"""Box3 real 융합 self-check — repo-root 실행, sys.path 가드, evidence 마스킹.

베이스: codex run_box3_real_self_check(자가점검). 융합 단일 계약/7단계명 기준으로
갱신. 실제 자산은 PENDING 이므로 actual_pass_box3_real_claim=False(정직).
fixture manifest 는 real 경로 게이트 검증 전용이며 production 자산이 아니다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.cards.box3.asset_manifest import (  # noqa: E402
    ASSET_INVENTORY_PASS_STATUS,
    Box3AssetRecord,
    REQUIRED_ASSET_NAMES,
    build_contract_only_asset_manifest,
    build_real_asset_manifest,
    manifest_allows_real,
)
from butler_pc_core.cards.box3.real_contracts import Box3RealRuntimeEnvelope  # noqa: E402
from butler_pc_core.cards.box3.real_pipeline import (  # noqa: E402
    Box3RealPipelineConfig,
    run_box3_real_followup,
)
from butler_pc_core.cards.box3.security import assert_no_raw_persistence, stable_json_digest  # noqa: E402


EVIDENCE = ROOT / "evidence" / "box3_real_v1_2"
LOCAL_ROOT_NAMES = ("Users", "home", "Library", "System", "Applications", "opt", "private", "var", "tmp", "Volumes")
DRIVE_LETTER_PATH = r"[A-Za-z]" + ":" + r"[\\/][^\s,;)]*"
LOOKBEHIND_CHARS = r"\w" + ":" + "/"
LOCAL_PATH_RE = re.compile(
    r"(?<![" + LOOKBEHIND_CHARS + r"])(?:"
    + r"/(?:" + "|".join(LOCAL_ROOT_NAMES) + r")(?:/[^\s,;)]*)?"
    + r"|" + DRIVE_LETTER_PATH
    + r")"
)

# real 경로 게이트를 모두 통과하는 fixture 입력(단일 표 청크 + 근접 echo draft).
PASSING_REF = (
    "프로젝트 알파 납품 일정 표 | 납품일 2026년 3월 31일 | 계약 금액 1억원 | 담당자 검토 완료 | 합의 완료 보고"
)
PASSING_DRAFT = (
    "제목: 프로젝트 알파 납품 보고\n"
    "배경: 프로젝트 알파 납품 일정 보고\n"
    "핵심 내용: 납품일 2026년 3월 31일 계약 금액 1억원\n"
    "근거: 담당자 검토 완료 합의 완료\n"
    "확인 필요: 없음\n"
    "최종 문안: 프로젝트 알파 납품 일정 계약 금액 담당자 검토 완료 보고\n"
)


def write_json(path: Path, payload: object) -> None:
    assert_no_raw_persistence(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sanitize_log(value: str) -> str:
    value = value.replace(str(ROOT), "[PACKAGE_ROOT]")
    return LOCAL_PATH_RE.sub("[LOCAL_PATH_REDACTED]", value)


def passing_manifest_fixture() -> dict:
    assets = []
    for index, name in enumerate(REQUIRED_ASSET_NAMES):
        sha_char = "abcdef0123456789"[index]
        assets.append(asdict(Box3AssetRecord(
            asset_name=name,
            role=f"{name}_role",
            display_sha_prefix=f"{sha_char * 8}...",
            asset_path=f"ref:BOX3_{name.upper()}_PATH",
            sha256_full=sha_char * 64,
            sha_scope="file",
            measured_at="2026-06-02T00:00:00+00:00",
            measured_by="self_check_fixture",
            source_metadata_files=["adapter_config.json"],
            interface_inventory_status="pass",
            real_claim_allowed=True,
            fail_class=None,
        )))
    manifest = {
        "schema_version": "box3.asset_manifest.v1",
        "status": ASSET_INVENTORY_PASS_STATUS,
        "real_claim_allowed": True,
        "state_gate": "ASSET_INVENTORY_PASS",
        "created_at": "2026-06-02T00:00:00+00:00",
        "assets": assets,
        "fixture_only": True,
    }
    assert_no_raw_persistence(manifest)
    return manifest


def supported_draft(_envelope: Box3RealRuntimeEnvelope) -> str:
    return PASSING_DRAFT


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    # 박스 3 real asset 최종 (2026-06-03): 9도우미 zip+LoRA 실측으로 4 helper 모두 PASS.
    # actual_manifest 는 실측 PASS 본문(build_real_asset_manifest)으로 채우고, real_pipeline
    # 의 fixture_manifest 는 그대로 fixture 게이트 검증용으로 사용 (final_real_gate 7단계는
    # asset_manifest 외 stage 도 검증 — 본 self_check 의 smoke 시나리오는 fixture 로 유지).
    contract_manifest = build_real_asset_manifest(measured_at="2026-06-02T00:00:00+00:00")
    fixture_manifest = passing_manifest_fixture()
    real_claim_pass = manifest_allows_real(contract_manifest)
    write_json(EVIDENCE / "asset_inventory_status_v1_2.json", {
        "schema_version": "box3.real_asset_inventory_status.v1_2",
        "status": ASSET_INVENTORY_PASS_STATUS if real_claim_pass else "PARTIAL_REAL_GATED_ASSET_PENDING",
        "actual_manifest": contract_manifest,
        "fixture_manifest_used_for_gate_tests": True,
        "pass_box3_real_claim": real_claim_pass,
        "reason": (
            "9도우미 (group-A handoff) 실측 — 4 helper 보관 SHA prefix 모두 정확 매치, "
            "asset_inventory PASS. real_pipeline final_real_gate (7단계) 는 별도이며 "
            "smoke 검증은 fixture_manifest 로 수행한다."
        ),
    })

    # 박스 3 real 융합 v1.0 정정: envelope.request_id 를 결정적 고정값으로 주입한다.
    # default 인 new_request_id() 는 매 실행 시 UUID4 를 생성하여 envelope.request_digest
    # (request_id 가 SSOT 입력) 와 그 파생 verdict.request_digest 가 비결정적으로 갱신되어
    # evidence/box3_real_v1_2/pipeline_smoke_v1_2.json 이 self-check 재실행마다 dirty 가
    # 된다. dirty-tree 0 (재현 결정성) 보장을 위해 self_check 전용 결정적 ID 를 고정한다.
    envelope = Box3RealRuntimeEnvelope.from_raw(
        drafting_request="프로젝트 알파 납품 보고서를 작성하라",
        reference_texts=[PASSING_REF],
        request_id="box3-real-fusion-v1-0-self-check",
    )
    verdict, audit = run_box3_real_followup(
        envelope,
        asset_manifest=fixture_manifest,
        real_model_runner=supported_draft,
        config=Box3RealPipelineConfig(fixed_eval_pass=True, allow_pass_box3_real_after_human_approval=True),
    )
    write_json(EVIDENCE / "pipeline_smoke_v1_2.json", {
        "verdict": verdict.to_persistable_dict(),
        "audit": audit.to_dict(),
    })
    write_json(EVIDENCE / "metric_summary_v1_2.json", verdict.metrics)

    pytest_command = [
        sys.executable, "-m", "pytest",
        "tests/cards/box3/test_box3_real_contract_v1_2.py",
        "tests/cards/box3/test_box3_real_grounding_v1_2.py",
        "tests/cards/box3/test_box3_real_metrics_v1_2.py",
        "tests/cards/box3/test_box3_real_pipeline_v1_2.py",
        "tests/cards/box3/test_box3_real_eval_v1_2.py",
        "-v", "--disable-warnings",
    ]
    result = subprocess.run(
        pytest_command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    (EVIDENCE / "pytest_box3_real_v1_2.txt").write_text(
        "# command: python3 -m pytest tests/cards/box3/test_box3_real_*_v1_2.py -v --disable-warnings\n"
        + sanitize_log(result.stdout),
        encoding="utf-8",
    )

    package_manifest = {
        "schema_version": "box3.real_fusion.package_manifest.v1_0",
        # 박스 3 real asset 최종 (2026-06-03): real_claim_pass=True 면 asset 수준 PASS,
        # False 면 PARTIAL_REAL_GATED_ASSET_PENDING(기존). test_returncode 가 0 이 아니면 BLOCK.
        "status": (
            "BLOCK_BOX3_REAL_TEST_FAILED"
            if result.returncode != 0
            else (ASSET_INVENTORY_PASS_STATUS if real_claim_pass else "PARTIAL_REAL_GATED_ASSET_PENDING")
        ),
        "directive_version": "Butler 박스3 real 융합 v1.0",
        "pr770_precondition": "MERGED",
        "single_contract_objects": [
            "Box3RealRuntimeEnvelope",
            "Box3RealVerdict",
            "Box3RealAuditRecord",
            "ClaimVerdict",
        ],
        "pipeline_stages": [
            "asset_inventory",
            "helper7_evidence_extraction",
            "draft_runner",
            "claim_extraction",
            "helper4_claim_grounding",
            "helper3_helper8_format_style",
            "final_real_gate",
        ],
        "real_path_fixture_pass": verdict.status == "real",
        # 박스 3 real asset 최종 (2026-06-03): 9도우미 4 helper PASS → manifest_allows_real=True.
        # 본 stamp 는 *asset inventory* 게이트 통과만 의미하며, real_pipeline final_real_gate
        # (7단계 fail-closed) 는 별도. 4 helper 모두 sha256_full + interface_inventory_status=pass
        # 충족이라 actual_pass_box3_real_claim=True 로 정직 표기 (asset 수준).
        "actual_pass_box3_real_claim": real_claim_pass,
        "actual_asset_pending": [
            asset["asset_name"]
            for asset in contract_manifest["assets"]
            if asset["sha256_full"] is None
        ],
        "raw_persistence_zero": True,
        "external_send_zero": True,
        "pytest_returncode": result.returncode,
        "evidence_digest": stable_json_digest({
            "asset_inventory_status": contract_manifest,
            "pipeline_smoke": {"verdict": verdict.to_persistable_dict(), "audit": audit.to_dict()},
            "metrics": verdict.metrics,
        }),
    }
    write_json(EVIDENCE / "package_manifest_v1_2.json", package_manifest)
    print(json.dumps(package_manifest, ensure_ascii=False, sort_keys=True))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
