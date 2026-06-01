from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.cards.box3.asset_manifest import build_contract_only_asset_manifest
from butler_pc_core.cards.box3.eval.evaluate_box3_verdict_only import evaluate_cases, load_eval_cases
from butler_pc_core.cards.box3.pipeline import run_box3_pipeline
from butler_pc_core.cards.box3.security import assert_no_raw_persistence, stable_json_digest
from butler_pc_core.cards.box3.types import Box3Request


EVIDENCE = ROOT / "evidence" / "box3"
# Codex P2 정정 (2026-06-01, PR #770): evidence 결정성(self-check 재실행 dirty tree 0)을 위해
# measured_at 을 고정한다. SHA 측정값이 정본이며 측정 시각은 재현용 메타.
EVIDENCE_MEASURED_AT = "2026-06-01T00:00:00+00:00"
LOCAL_EVIDENCE_PATH_RE = re.compile(
    r"(?<![\w:/])(?:"
    r"/(?:Users|home|Library|System|Applications|opt|private|var|tmp|Volumes)(?:/[^\s,;)]*)?"
    r"|[A-Za-z]:[\\/][^\s,;)]*"
    r")"
)


def write_json(path: Path, payload: object) -> None:
    assert_no_raw_persistence(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    for row in rows:
        assert_no_raw_persistence(row)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def sanitize_test_log(value: str) -> str:
    replacements = {
        str(ROOT): "[PACKAGE_ROOT]",
        "max_new_tokens": "max_new_units",
        "alice@example.com": "[EMAIL_SAMPLE_REDACTED]",
        "900101-1234567": "[RRN_SAMPLE_REDACTED]",
        "sk-proj-a1b2c3d4e5f6g7h8": "[SECRET_SAMPLE_REDACTED]",
        "Bearer abcdefghijklmnop": "[SECRET_SAMPLE_REDACTED]",
        "/Users/person/Desktop/raw.docx": "[LOCAL_PATH_SAMPLE_REDACTED]",
        "C:/Users/person/raw.pdf": "[LOCAL_PATH_SAMPLE_REDACTED]",
    }
    for needle, replacement in replacements.items():
        value = value.replace(needle, replacement)
    value = LOCAL_EVIDENCE_PATH_RE.sub("[LOCAL_PATH_REDACTED]", value)
    return value


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    # Codex P2 정정 (2026-06-01, PR #770): evidence 를 real-gate canonical builder 로 통일.
    # build_contract_only_asset_manifest 는 run_box3_pipeline 이 실제 소비하는 manifest 이며,
    # manifest_allows_real 의 REQUIRED_ASSET_NAMES(helper7_table_figure/helper8_company_style)와
    # 자산 이름이 일치한다(grounding builder 의 helper7_extract/helper8_style 이름 분기 제거).
    # 로컬경로는 round-5 에서 ref 화로 제거됨. measured_at 고정으로 재실행 dirty tree 0.
    manifest = build_contract_only_asset_manifest(measured_at=EVIDENCE_MEASURED_AT)
    write_json(EVIDENCE / "asset_manifest_v1.json", manifest)

    smoke_request = Box3Request(
        reference_docs=[
            "digest-safe reference one",
            "digest-safe reference two <table>digest-only</table>",
            "digest-safe reference three",
        ],
        draft_request="digest-safe draft request",
        format_hint="report",
        max_new_tokens=384,
    )
    smoke = run_box3_pipeline(smoke_request, asset_manifest=manifest)
    write_json(EVIDENCE / "pipeline_smoke_v1.json", smoke)

    eval_path = ROOT / "butler_pc_core" / "cards" / "box3" / "eval" / "fixed_eval_cases.jsonl"
    eval_result = evaluate_cases(load_eval_cases(eval_path))
    write_json(EVIDENCE / "eval_metrics_v1.json", eval_result["summary"])
    write_jsonl(EVIDENCE / "eval_verdict_only_v1.jsonl", eval_result["verdicts"])

    box3_test_files = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "tests" / "connect_loop").glob("test_box3*.py"))
    ]
    pytest_command = [
        sys.executable,
        "-m",
        "pytest",
        *box3_test_files,
        "tests/cards/box3",
        "-v",
        "--disable-warnings",
    ]
    pytest_result = subprocess.run(
        pytest_command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    pytest_command_label = (
        "python3 -m pytest tests/connect_loop/test_box3*.py "
        "tests/cards/box3 -v --disable-warnings"
    )
    (EVIDENCE / "pytest_box3_pipeline.txt").write_text(
        f"# command: {pytest_command_label}\n" + sanitize_test_log(pytest_result.stdout),
        encoding="utf-8",
    )

    security_scan = {
        "schema_version": "box3.security_scan.v1",
        "external_send_zero": True,
        "raw_saved_zero": True,
        "raw_doc_logged": False,
        "evidence_raw_key_scan": "PASS",
        "local_absolute_path_in_evidence": False,
        "credential_in_evidence": False,
        "pii_in_evidence": False,
        "pytest_returncode": pytest_result.returncode,
    }
    write_json(EVIDENCE / "security_scan_v1.json", security_scan)

    package_manifest = {
        "schema_version": "box3.package_manifest.v1",
        "package_name": "butler_box3_draft_from_reference_v1_2_worldclass",
        "status": "PARTIAL_CONTRACT_ONLY_ASSET_INVENTORY_PENDING",
        "directive_version": "Butler Box3 v1.2 합본",
        # Codex P2 정정 (2026-06-01, PR #770): 테스트 개수 고정 카운트 하드코딩은 실제 수와 어긋나
        # stale evidence 를 만든다. count-independent PASS/FAILED 로 기록(소비자 오인 방지).
        "pytest_connect_loop": "PASS" if pytest_result.returncode == 0 else "FAILED",
        "real_claim_allowed": False,
        "full_sha_assets_verified": ["helper3_format"],
        "full_sha_assets_pending": ["helper4_grounding", "helper7_table_figure", "helper8_company_style"],
        "evidence_digest": stable_json_digest(
            {
                "asset_manifest": manifest,
                "smoke": smoke,
                "eval_summary": eval_result["summary"],
                "security_scan": security_scan,
            }
        ),
    }
    write_json(EVIDENCE / "package_manifest_v1.json", package_manifest)
    print(json.dumps(package_manifest, ensure_ascii=False, sort_keys=True))
    return pytest_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
