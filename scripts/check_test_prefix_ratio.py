#!/usr/bin/env python3
"""check_test_prefix_ratio.py — 테스트 prefix 비율 게이트.

pytest --collect-only 결과를 파싱하여 각 prefix 비율이 기준을 충족하는지 확인한다.

기준 (±5% 허용):
  happy      30%
  boundary   30%
  adv        30%
  concurrent 10%
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

TARGETS = {
    "happy": 0.30,
    "boundary": 0.30,
    "adv": 0.30,
    "concurrent": 0.10,
}
TOLERANCE = 0.05
KNOWN_PREFIXES = set(TARGETS.keys())

_TEST_NAME_RE = re.compile(r"<Function\s+(test_\S+)>")


def collect_test_names(test_dir: str = "tests") -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_dir, "--collect-only", "-q", "--no-header"],
        capture_output=True,
        text=True,
    )
    names = []
    for line in result.stdout.splitlines():
        # 형식: "tests/foo.py::test_happy_xxx" 또는 "  <Function test_happy_xxx>"
        m = _TEST_NAME_RE.search(line)
        if m:
            names.append(m.group(1))
        elif "::" in line:
            parts = line.strip().split("::")
            if parts:
                names.append(parts[-1].strip())
    return [n for n in names if n.startswith("test_")]


def classify(name: str) -> str:
    for prefix in KNOWN_PREFIXES:
        if name.startswith(f"test_{prefix}_"):
            return prefix
    return "other"


def check_ratios(names: list[str]) -> bool:
    if not names:
        print("ERROR: 수집된 테스트가 없습니다.", file=sys.stderr)
        return False

    counts = Counter(classify(n) for n in names)
    prefixed_total = sum(counts.get(p, 0) for p in TARGETS)
    other = counts.get("other", 0)

    print(f"총 테스트: {len(names)}  (prefix 있음: {prefixed_total}, 기타: {other})")
    if prefixed_total == 0:
        print("ERROR: prefix 있는 테스트가 없습니다.", file=sys.stderr)
        return False

    print(f"{'prefix':<12} {'count':>6}  {'actual':>7}  {'target':>7}  {'pass':>5}")
    print("-" * 48)

    all_pass = True
    for prefix, target in TARGETS.items():
        count = counts.get(prefix, 0)
        actual = count / prefixed_total
        ok = abs(actual - target) <= TOLERANCE
        status = "OK" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"{prefix:<12} {count:>6}  {actual:>6.1%}  {target:>6.1%}  {status:>5}")

    if other:
        print(f"\n기타(미분류): {other}개 — 비율 계산에서 제외됩니다.")

    return all_pass


def main() -> int:
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "tests"
    names = collect_test_names(test_dir)
    passed = check_ratios(names)
    if not passed:
        print("\n비율 기준 미달 — 테스트를 추가하거나 리밸런싱하십시오.", file=sys.stderr)
        return 1
    print("\n모든 prefix 비율 기준 충족.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
