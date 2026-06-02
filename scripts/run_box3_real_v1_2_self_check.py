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

    contract_manifest = build_contract_only_asset_manifest(measured_at="2026-06-02T00:00:00+00:00")
    fixture_manifest = passing_manifest_fixture()
    write_json(EVIDENCE / "asset_inventory_status_v1_2.json", {
        "schema_version": "box3.real_asset_inventory_status.v1_2",
        "status": "PARTIAL_REAL_GATED_ASSET_PENDING",
        "actual_manifest": contract_manifest,
        "fixture_manifest_used_for_gate_tests": True,
        "pass_box3_real_claim": False,
        "reason": "helper4/helper7/helper8 full SHA and interface smoke are not measured in this repo state",
    })

    envelope = Box3RealRuntimeEnvelope.from_raw(
        drafting_request="프로젝트 알파 납품 보고서를 작성하라",
        reference_texts=[PASSING_REF],
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
        "status": "PARTIAL_REAL_GATED_ASSET_PENDING" if result.returncode == 0 else "BLOCK_BOX3_REAL_TEST_FAILED",
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
        "actual_pass_box3_real_claim": False,
        "actual_asset_pending": ["helper4_grounding", "helper7_table_figure", "helper8_company_style"],
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
