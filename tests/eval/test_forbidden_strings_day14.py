"""PR #716 사전 점검 — evidence/day14 forbidden 10패턴 0건 자동 검증."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAY14 = ROOT / "evidence/day14"

FORBIDDEN_PATTERNS = [
    r"production candidate approved",
    r"PRODUCTION_CANDIDATE_PASS",
    r"release ready",
    r"beta ready",
    r"external beta ready",
    r"auto_apply_accuracy",
    r"card1_gold_v1\b",
    r"BUTLER_INTEGRATION_READY",
    r"PROCEED",
    r"최종 승인",
]


def test_forbidden_strings_absent_day14():
    if not DAY14.exists():
        return  # evidence 아직 미생성 — 다른 회귀에서 검증
    pattern = "|".join(FORBIDDEN_PATTERNS)
    res = subprocess.run(
        ["grep", "-RInE", pattern, str(DAY14)],
        capture_output=True, text=True,
    )
    # exit 1 = no match (정상). exit 0 = match 있음 (위반).
    assert res.returncode == 1, (
        f"forbidden strings 발견:\n{res.stdout[:2000]}"
    )
