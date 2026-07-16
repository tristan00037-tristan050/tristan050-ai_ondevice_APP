#!/usr/bin/env python3
"""그룹A용 — 통장 엑셀 한 개를 넣으면 '기존 분류기 vs 새 분류기(shadow)' 비교표를 만든다.

새 분류기 결과는 기록만 한다. 기존 분류(제품)에는 아무 영향이 없다. 원문·상호명·계좌번호는
저장하지 않고 필요한 것만 digest(해시)로 남긴다. 자동기표는 잠긴 상태(JOURNAL_AUTO_POST_ALLOWED=NO).

사용법:
    python3 scripts/box5_shadow_compare.py 통장.xlsx
    python3 scripts/box5_shadow_compare.py 통장.xlsx --out 결과폴더

산출:
    <out>/box5_shadow_compare.csv    ← 사람이 보는 비교표(엑셀로 열림)
    <out>/box5_shadow_compare.jsonl  ← 기계가 읽는 원자료
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# butler_pc_core 를 자동 탐색: 저장소 루트 → 설치된 앱 Resources → 환경변수.
# (그룹A가 PYTHONPATH 를 몰라도 실행되게 한다.)
def _bootstrap_import_path() -> None:
    candidates = [
        Path(__file__).resolve().parents[1],  # 저장소 루트 (scripts/ 의 부모)
        Path("/Applications/Butler.app/Contents/Resources"),  # 설치된 앱 번들
    ]
    env_root = __import__("os").environ.get("BUTLER_PC_CORE_ROOT")
    if env_root:
        candidates.insert(0, Path(env_root))
    for root in candidates:
        if (root / "butler_pc_core" / "__init__.py").is_file():
            sys.path.insert(0, str(root))
            return
    # 없으면 기본 동작(현재 sys.path)에 맡긴다.


_bootstrap_import_path()

from butler_pc_core.accounting.classifier import classify_file  # noqa: E402
from butler_pc_core.accounting.classify.shadow import run_shadow_over_dataframe  # noqa: E402
from butler_pc_core.company_profile.storage import CompanyProfileStore, ProfileLoadError  # noqa: E402

_FIELDS = [
    "transaction_key", "legacy_status", "legacy_account_id",
    "shadow_status", "shadow_account_id", "shadow_rule_id",
    "shadow_rule_digest", "shadow_reason_code", "agreement", "shadow_error_code",
]


def _load_active_profile():
    return CompanyProfileStore().load_active_profile()


def _classify_product_baseline(src: Path, company_profile):
    return classify_file(str(src), company_profile=company_profile)


def main() -> int:
    ap = argparse.ArgumentParser(description="Box5 3단계 shadow 비교표 생성 (관찰 전용)")
    ap.add_argument("excel", help="통장 거래내역 파일 (.xlsx/.xls/.csv)")
    ap.add_argument("--out", default=".", help="결과를 저장할 폴더 (기본: 현재 폴더)")
    args = ap.parse_args()

    src = Path(args.excel)
    if not src.is_file():
        print(f"❌ 파일을 찾을 수 없습니다: {src}")
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("1) 기존 분류기 실행(제품과 동일 경로)…")
    try:
        # ★ 활성 profile 을 한 번만 로드해 legacy·shadow 양쪽에 같은 객체로 전달한다.
        company_profile = _load_active_profile()
    except ProfileLoadError:
        print("ERROR_CODE=COMPANY_PROFILE_LOAD_FAILED", file=sys.stderr)
        return 1
    df = _classify_product_baseline(src, company_profile)

    print("2) 새 분류기를 나란히 실행(shadow, 기록만)…")
    # ★ shadow 에도 동일 profile 전달 → self-transfer guard 가 CLI 경로에서도 작동.
    records = run_shadow_over_dataframe(df, company_profile)

    csv_path = out_dir / "box5_shadow_compare.csv"
    jsonl_path = out_dir / "box5_shadow_compare.jsonl"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDS)
        writer.writeheader()
        for rec in records:
            row = rec.to_safe_dict()
            writer.writerow({k: row.get(k, "") for k in _FIELDS})
    with jsonl_path.open("w", encoding="utf-8") as fh:
        fh.write("".join(rec.to_jsonl() + "\n" for rec in records))

    # 요약 집계
    tally: dict[str, int] = {}
    for rec in records:
        tally[rec.agreement] = tally.get(rec.agreement, 0) + 1
    print(f"\n✅ 완료 — 거래 {len(records)}건")
    print(f"   비교표(csv):  {csv_path}")
    print(f"   원자료(jsonl): {jsonl_path}")
    print("   일치 요약:")
    for key in sorted(tally):
        print(f"     {key}: {tally[key]}건")
    print("\n※ 새 분류기 결과는 기록만 했습니다. 기존 분류 결과·엑셀은 바뀌지 않았습니다.")
    print("※ 원문·상호명·계좌번호는 저장하지 않았습니다(필요분만 digest).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
