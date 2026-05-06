"""단독 실행 진입점 — 회계 분류 테스트 + 디버깅."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from butler_pc_core.accounting.classifier import classify_file, save_classified
from butler_pc_core.accounting.report import build_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Butler 회계 분류 CLI")
    parser.add_argument("input", help="입력 파일 (.xlsx/.csv/.xls)")
    parser.add_argument("-o", "--output", default=None,
                        help="출력 xlsx 경로 (기본: <input>_classified.xlsx)")
    parser.add_argument("--summary", action="store_true", help="분류 요약 출력")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"오류: 파일이 없습니다 — {in_path}", file=sys.stderr)
        sys.exit(1)

    print(f"분류 중: {in_path}")
    df = classify_file(in_path)

    out_path = Path(args.output) if args.output else in_path.with_stem(in_path.stem + "_classified")
    out_path = out_path.with_suffix(".xlsx")
    save_classified(df, out_path)
    print(f"저장됨: {out_path}")

    if args.summary:
        summary = build_summary(df)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
