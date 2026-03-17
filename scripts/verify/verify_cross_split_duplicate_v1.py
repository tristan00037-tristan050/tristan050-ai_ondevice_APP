#!/usr/bin/env python3
"""
verify_cross_split_duplicate_v1.py — cross-split leakage 검증
train / validation / test JSONL 파일 사이에 (prompt, completion) 중복 행이 없는지 확인

실행:
  python3 scripts/verify/verify_cross_split_duplicate_v1.py
  python3 scripts/verify/verify_cross_split_duplicate_v1.py --data-dir data/synthetic_v40

완료 기준:
  DATASET_CROSS_SPLIT_DUPLICATE_0_OK=1
  CROSS_SPLIT_REQUIRED_FILES_PRESENT_OK=1
  CROSS_SPLIT_DUPLICATE_NO_RAW_LOG_OK=1
  CROSS_SPLIT_DUPLICATE_SIGNAL_SINGLE_SOURCE_OK=1
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def pair_digest(prompt: str, completion: str) -> str:
    """(prompt, completion) 쌍의 SHA256 digest 반환 (raw 텍스트 대신 사용)."""
    payload = json.dumps({"prompt": prompt, "completion": completion}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_pairs(path: Path) -> set[tuple[str, str]]:
    """JSONL 파일에서 (prompt, completion) 튜플 set 반환.
    파일 없음/빈 파일/빈 레코드는 RuntimeError로 fail-closed 처리."""
    if not path.exists():
        raise RuntimeError(f"SPLIT_FILE_MISSING:{path.name}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"SPLIT_FILE_EMPTY:{path.name}")

    pairs: set[tuple[str, str]] = set()
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"BLOCK: JSON 파싱 실패 — {path}:{i}: {e}", file=sys.stderr)
            sys.exit(1)
        prompt = row.get("prompt", "")
        completion = row.get("completion", "")
        if not prompt or not completion:
            raise RuntimeError(f"SPLIT_RECORD_INVALID:{path.name}:{i}")
        pairs.add((prompt, completion))
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
    try:
        for split in splits:
            path = data_dir / f"{split}.jsonl"
            split_pairs[split] = load_pairs(path)
            print(f"  {split}.jsonl: {len(split_pairs[split])} 건 로드")
    except RuntimeError as e:
        print(f"BLOCK: {e}", file=sys.stderr)
        sys.exit(1)

    print("CROSS_SPLIT_REQUIRED_FILES_PRESENT_OK=1")

    # 모든 split 쌍에 대해 교집합 확인
    checked_pairs = [
        ("train", "validation"),
        ("train", "test"),
        ("validation", "test"),
    ]
    found_leak = False
    for a, b in checked_pairs:
        overlap = split_pairs[a] & split_pairs[b]
        if overlap:
            found_leak = True
            overlap_digests = [pair_digest(p, c) for p, c in overlap]
            print(f"ERROR_CODE=CROSS_SPLIT_DUPLICATE_FOUND", file=sys.stderr)
            print(f"SPLIT_A={a}", file=sys.stderr)
            print(f"SPLIT_B={b}", file=sys.stderr)
            print(f"DUPLICATE_COUNT={len(overlap)}", file=sys.stderr)
            print(f"FIRST_DUPLICATE_DIGEST={sorted(overlap_digests)[0]}", file=sys.stderr)

    if found_leak:
        print("DATASET_CROSS_SPLIT_DUPLICATE_0_OK=0")
        sys.exit(1)

    print("CROSS_SPLIT_DUPLICATE_NO_RAW_LOG_OK=1")
    print("DATASET_CROSS_SPLIT_DUPLICATE_0_OK=1")
    print("CROSS_SPLIT_DUPLICATE_SIGNAL_SINGLE_SOURCE_OK=1")
    sys.exit(0)


if __name__ == "__main__":
    main()
