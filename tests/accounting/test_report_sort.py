"""test_report_sort.py — md_content 보고서 정렬 검증 (양수 상단, 음수 하단)."""
from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

_skip = pytest.mark.skipif(not _DEPS_OK, reason="fastapi 미설치")

# 입출금 분리 컬럼 CSV → _amt = 입금 - 출금 → total_amount가 실제 양수/음수로 계산됨
_CSV_MIXED = (
    "적요,출금,입금,거래처\n"
    "급여 지급,2500000,,\n"
    "매출 입금,,5000000,고객사A\n"
    "통신비 납부,88000,,KT\n"
    "이자 수입,,120000,\n"
).encode("utf-8")


def _get_md_content(csv_bytes: bytes) -> str:
    """CSV 분류 요청을 수행하고 complete 이벤트의 md_content를 반환."""
    import json
    import tempfile
    from pathlib import Path
    from butler_sidecar import app

    client = TestClient(app)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(csv_bytes)
        csv_path = f.name
    try:
        with open(csv_path, "rb") as fp:
            resp = client.post(
                "/accounting/classify",
                files={"file": ("test_sort.csv", fp, "text/csv")},
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
    finally:
        Path(csv_path).unlink(missing_ok=True)

    for line in resp.text.splitlines():
        if line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
                if "md_content" in data:
                    return data["md_content"]
            except json.JSONDecodeError:
                pass
    return ""


@_skip
def test_report_positive_amounts_before_negative():
    """md_content 보고서 표에서 양수 금액 행이 음수 금액 행보다 앞에 위치해야 한다."""
    md = _get_md_content(_CSV_MIXED)
    assert md, "md_content가 비어 있음"

    # 금액 패턴 찾기: 양수(쉼표 없이/있음)와 음수(−부호) 행의 위치 비교
    lines = md.splitlines()
    table_lines = [l for l in lines if l.startswith("|") and "원" in l]
    assert table_lines, "금액 포함 테이블 행 없음"

    first_negative_idx = None
    first_positive_idx = None
    for idx, line in enumerate(table_lines):
        cells = [c.strip() for c in line.split("|")]
        for cell in cells:
            if cell.startswith("-") and "원" in cell and first_negative_idx is None:
                first_negative_idx = idx
            elif "원" in cell and not cell.startswith("-") and cell != "합계금액" and first_positive_idx is None:
                first_positive_idx = idx

    assert first_positive_idx is not None, "양수 금액 행 없음"
    assert first_negative_idx is not None, "음수 금액 행 없음"
    assert first_positive_idx < first_negative_idx, (
        f"양수 행(idx={first_positive_idx})이 음수 행(idx={first_negative_idx})보다 뒤에 위치"
    )


@_skip
def test_report_amounts_descending_within_sign_group():
    """같은 부호 그룹 내에서 절댓값 내림차순 정렬이 되어야 한다 (큰 금액이 먼저)."""
    md = _get_md_content(_CSV_MIXED)
    assert md, "md_content가 비어 있음"

    lines = md.splitlines()
    table_lines = [l for l in lines if l.startswith("|") and "원" in l]
    assert table_lines, "금액 포함 테이블 행 없음"

    import re
    amounts = []
    for line in table_lines:
        cells = [c.strip() for c in line.split("|")]
        for cell in cells:
            m = re.search(r"(-?)([0-9,]+)원", cell)
            if m:
                sign = -1 if m.group(1) else 1
                val = sign * int(m.group(2).replace(",", ""))
                amounts.append(val)
                break

    if not amounts:
        pytest.skip("금액 파싱 실패 — 분류 결과 없음")

    positives = [a for a in amounts if a >= 0]
    negatives = [a for a in amounts if a < 0]

    # 양수 그룹 내림차순 확인
    if len(positives) > 1:
        assert positives == sorted(positives, reverse=True), (
            f"양수 그룹 내림차순 정렬 실패: {positives}"
        )
    # 음수 그룹 절댓값 내림차순 확인
    if len(negatives) > 1:
        abs_negatives = [abs(a) for a in negatives]
        assert abs_negatives == sorted(abs_negatives, reverse=True), (
            f"음수 그룹 절댓값 내림차순 정렬 실패: {negatives}"
        )
