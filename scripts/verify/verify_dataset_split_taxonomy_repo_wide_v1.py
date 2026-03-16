#!/usr/bin/env python3
"""
verify_dataset_split_taxonomy_repo_wide_v1.py — 보강 1
레포 전역 split taxonomy 전수 검사
val alias 금지 / train|validation|test 통일 확인

검사 범위:
  - scripts/ai/*.py
  - scripts/verify/*.sh
  - scripts/verify/*.py
  - data/sanity/*.jsonl
  - docs/**/*.md (split 예시 포함 파일)

실행:
  python3 scripts/verify/verify_dataset_split_taxonomy_repo_wide_v1.py
  python3 scripts/verify/verify_dataset_split_taxonomy_repo_wide_v1.py --root /path/to/repo

완료 기준:
  DATASET_SPLIT_TAXONOMY_REPO_WIDE_OK=1
  DATASET_SPLIT_TAXONOMY_V1_OK=1
  VAL_ALIAS_FORBIDDEN_OK=1
"""

import argparse
import json
import re
import sys
from pathlib import Path

VALID_SPLITS  = {"train", "validation", "test"}

# "split": "val" 패턴 — validation 이 아닌 단독 val
INVALID_ALIAS = re.compile(r'"split"\s*:\s*"val"(?!idation)')

# 리스트 안의 "val" — ["train", "val", "test"] 형태
VAL_IN_LIST   = re.compile(r'[\[,\s]"val"[\],\s]')

# random.choices(["train","val",...]) 형태
VAL_IN_CHOICES = re.compile(r'choices\s*\(\s*\[.*?"val".*?\]')


def check_text_file(path: Path) -> list[str]:
    """py / sh / md 파일에서 val alias 탐지"""
    errors = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        errors.append(f"READ_ERROR {path}: {e}")
        return errors

    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        # 주석 라인 스킵 (# 또는 //)
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        # "BEFORE — DO NOT USE" 또는 "noqa" 주석이 있는 줄은 예시 코드로 간주 — 스킵
        if "BEFORE" in line or "noqa" in line.lower() or "DO NOT USE" in line:
            continue
        # .md 파일에서 "수정 전/후" 예시 문맥 라인 스킵
        if path.suffix == ".md" and (
            "수정 전" in line or "before" in line.lower() or "잘못된 값" in line
        ):
            continue
        if INVALID_ALIAS.search(line):
            errors.append(
                f"BLOCK: \"split\":\"val\" 금지 — {path}:{i}: {stripped}"
            )
        if VAL_IN_CHOICES.search(line):
            errors.append(
                f"BLOCK: choices에 \"val\" 금지 — {path}:{i}: {stripped}"
            )
        if VAL_IN_LIST.search(line):
            if "validation" not in line:
                errors.append(
                    f"BLOCK: 리스트에 \"val\" 금지 — {path}:{i}: {stripped}"
                )
    return errors


def check_jsonl_file(path: Path) -> list[str]:
    """JSONL 파일에서 split 필드 값 검사"""
    errors = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        errors.append(f"READ_ERROR {path}: {e}")
        return errors

    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            errors.append(f"BLOCK: JSON 파싱 실패 — {path}:{i}")
            continue
        split_val = row.get("split", "")
        if split_val and split_val not in VALID_SPLITS:
            errors.append(
                f"BLOCK: 유효하지 않은 split 값 '{split_val}' — {path}:{i}"
            )
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(
        description="레포 전역 split taxonomy 전수 검사"
    )
    ap.add_argument(
        "--root", default=None,
        help="레포 루트 경로 (기본: 스크립트 위치 기준 3단계 상위)"
    )
    args = ap.parse_args()

    if args.root:
        ROOT = Path(args.root).resolve()
    else:
        ROOT = Path(__file__).resolve().parent.parent.parent

    # 검사 대상 수집
    targets_text = [
        *ROOT.glob("scripts/ai/*.py"),
        *ROOT.glob("scripts/verify/*.sh"),
        *ROOT.glob("scripts/verify/*.py"),
        *ROOT.glob("docs/**/*.md"),
    ]
    targets_jsonl = [
        *ROOT.glob("data/sanity/*.jsonl"),
    ]

    all_errors: list[str] = []
    checked_files = 0

    for path in targets_text:
        errs = check_text_file(path)
        all_errors.extend(errs)
        checked_files += 1

    for path in targets_jsonl:
        errs = check_jsonl_file(path)
        all_errors.extend(errs)
        checked_files += 1

    print(f"검사 파일: {checked_files}개 "
          f"(py/sh/md: {len(targets_text)}, jsonl: {len(targets_jsonl)})")

    if all_errors:
        for e in all_errors:
            print(e, file=sys.stderr)
        print(f"\n오류: {len(all_errors)}건")
        print("DATASET_SPLIT_TAXONOMY_REPO_WIDE_OK=0")
        sys.exit(1)

    print("DATASET_SPLIT_TAXONOMY_REPO_WIDE_OK=1")
    print("DATASET_SPLIT_TAXONOMY_V1_OK=1")
    print("VAL_ALIAS_FORBIDDEN_OK=1")
    sys.exit(0)


if __name__ == "__main__":
    main()
