#!/usr/bin/env python3
"""
verify_cross_split_duplicate_v1.py — cross-split leakage 검증
train / validation / test JSONL 파일 사이에 (prompt, completion) 중복 행이 없는지 확인

실행:
  python3 scripts/verify/verify_cross_split_duplicate_v1.py
  python3 scripts/verify/verify_cross_split_duplicate_v1.py --data-dir data/synthetic_v40

완료 기준:
  DATASET_CROSS_SPLIT_DUPLICATE_0_OK=1
"""

import argparse
import json
import sys
from pathlib import Path


def load_pairs(path: Path) -> set[tuple[str, str]]:
    """JSONL 파일에서 (prompt, completion) 튜플 set 반환."""
    pairs: set[tuple[str, str]] = set()
    if not path.exists() or path.stat().st_size == 0:
        return pairs
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"BLOCK: JSON 파싱 실패 — {path}:{i}: {e}", file=sys.stderr)
            sys.exit(1)
        pairs.add((row.get("prompt", ""), row.get("completion", "")))
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser(
        description="cross-split (prompt, completion) 중복 검증"
    )
    ap.add_argument(
        "--data-dir", default=None,
        help="JSONL 파일이 있는 디렉토리 (기본: 레포 루트 기준 data/synthetic_v40)"
    )
    args = ap.parse_args()

    if args.data_dir:
        data_dir = Path(args.data_dir).resolve()
    else:
        data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic_v40"

    splits = ["train", "validation", "test"]
    split_pairs: dict[str, set[tuple[str, str]]] = {}
    for split in splits:
        path = data_dir / f"{split}.jsonl"
        split_pairs[split] = load_pairs(path)
        print(f"  {split}.jsonl: {len(split_pairs[split])} 건 로드")

    # 모든 split 쌍에 대해 교집합 확인
    leaks: list[str] = []
    checked_pairs = [
        ("train", "validation"),
        ("train", "test"),
        ("validation", "test"),
    ]
    for a, b in checked_pairs:
        overlap = split_pairs[a] & split_pairs[b]
        if overlap:
            for prompt, completion in sorted(overlap)[:5]:  # 최대 5건만 출력
                leaks.append(
                    f"BLOCK: cross-split 중복 ({a}↔{b}) "
                    f"prompt={prompt[:60]!r} completion={completion[:40]!r}"
                )
            if len(overlap) > 5:
                leaks.append(f"  ... 외 {len(overlap) - 5}건")

    if leaks:
        for msg in leaks:
            print(msg, file=sys.stderr)
        print("DATASET_CROSS_SPLIT_DUPLICATE_0_OK=0")
        sys.exit(1)

    print("DATASET_CROSS_SPLIT_DUPLICATE_0_OK=1")
    sys.exit(0)


if __name__ == "__main__":
    main()
