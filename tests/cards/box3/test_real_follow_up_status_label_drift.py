"""Codex HOLD 정정 회귀 (2026-06-04, PR #776) — Box3RealStatus Literal SSOT 6 정합.

본진 `real_pipeline_enablement.py::response_draft` 분기에 비정본 상태 문자열 (Literal
부재 라벨) 잔존 결함을 차단하기 위한 drift 회귀 잠금:

(1) 비정본 라벨 잔존 grep 0 (코드·테스트·evidence·schemas·scripts).
(2) `real_pipeline_enablement.py` 가 `decision.status in {...}` 형태로 비교하는 모든
    상태 문자열이 `typing.get_args(Box3RealStatus)` Literal 6 집합 안에 있는지 검증.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import get_args

import pytest

from butler_pc_core.cards.box3.real_contracts import Box3RealStatus


ROOT = Path(__file__).resolve().parents[3]


def test_runner_smoke_pass_label_grep_zero():
    """비정본 라벨이 코드·테스트·evidence 어디에도 잔존하지 않는다 (Literal drift 0)."""
    # needle 은 분할 표기로 self-매치 회피. 본 테스트 본문 안에 needle 직접 표기 0건.
    needle = "RUNNER_SMOKE" + "_PASS"
    scopes = [
        ROOT / "butler_pc_core",
        ROOT / "tests" / "cards" / "box3",
        ROOT / "evidence",
        ROOT / "schemas",
        ROOT / "scripts",
    ]
    self_path = Path(__file__).resolve()
    hits: list[str] = []
    for base in scopes:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.resolve() == self_path:
                continue
            if path.suffix not in {".py", ".sh", ".md", ".txt", ".json", ".jsonl"}:
                continue
            if "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if needle in text:
                hits.append(str(path.relative_to(ROOT)))
    assert hits == [], f"Literal-absent label still present in: {hits}"


def _extract_status_string_literals_from_status_membership(source: str) -> list[str]:
    """`decision.status in {"REAL_CANDIDATE", ...}` 형태의 set 원소 string literal 만 수집."""
    tree = ast.parse(source)
    collected: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        # `<left> in <right>` 또는 `<left> not in <right>` 형태 검사.
        if not node.ops or not isinstance(node.ops[0], (ast.In, ast.NotIn)):
            continue
        left = node.left
        # left 가 attribute access (예: decision.status / verdict.status 등) 인지 확인.
        if not isinstance(left, ast.Attribute):
            continue
        if left.attr not in {"status"}:
            continue
        right = node.comparators[0]
        if not isinstance(right, (ast.Set, ast.Tuple, ast.List)):
            continue
        for elt in right.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                collected.append(elt.value)
    return collected


def test_response_draft_branch_status_literals_match_box3_real_status_set():
    """`real_pipeline_enablement.py` 의 `decision.status in {...}` set 원소가 모두
    Box3RealStatus Literal SSOT 6 집합에 포함되는지 검증 (drift 0)."""
    target = ROOT / "butler_pc_core" / "cards" / "box3" / "real_pipeline_enablement.py"
    source = target.read_text(encoding="utf-8")
    membership_status_strings = _extract_status_string_literals_from_status_membership(source)
    assert membership_status_strings, (
        "no `decision.status in {...}` membership found in real_pipeline_enablement.py — "
        "expected at least the response_draft allowed-set."
    )
    allowed_labels = set(get_args(Box3RealStatus))
    drift = [s for s in membership_status_strings if s not in allowed_labels]
    assert drift == [], (
        f"status drift — labels not in Box3RealStatus Literal: {drift!r}. "
        f"allowed Literal: {sorted(allowed_labels)!r}"
    )


def test_box3_real_status_literal_has_exactly_six_ssot_labels():
    """Codex 보완 5 정합 — Box3RealStatus Literal SSOT **6** 라벨 고정."""
    labels = set(get_args(Box3RealStatus))
    expected = {
        "CONTRACT_ONLY",
        "ASSET_INVENTORY_PASS",
        "REAL_CANDIDATE",
        "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL",
        "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE",
        "BLOCKED",
    }
    assert labels == expected, f"SSOT drift: got {sorted(labels)!r}, expected {sorted(expected)!r}"


def _extract_response_draft_allowed_status_set(source: str) -> set[str]:
    """`response_draft = draft_text if decision.status in {...} else None` assignment
    안의 set 원소만 정밀 추출 (다른 status 비교는 본 set 과 별개)."""
    tree = ast.parse(source)
    collected: set[str] = set()
    for node in ast.walk(tree):
        # Assign: `response_draft = <IfExp(... in <Set>)>`
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        if node.targets[0].id != "response_draft":
            continue
        value = node.value
        if not isinstance(value, ast.IfExp):
            continue
        test = value.test
        if not isinstance(test, ast.Compare) or not isinstance(test.ops[0], (ast.In, ast.NotIn)):
            continue
        right = test.comparators[0]
        if not isinstance(right, (ast.Set, ast.Tuple, ast.List)):
            continue
        for elt in right.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                collected.add(elt.value)
    return collected


def test_response_draft_allowed_set_only_emits_pass_or_candidate():
    """response_draft 허용 set 안의 라벨이 정확히 {REAL_CANDIDATE,
    PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL} (정직 candidate 또는 PASS) — drift 0."""
    target = ROOT / "butler_pc_core" / "cards" / "box3" / "real_pipeline_enablement.py"
    source = target.read_text(encoding="utf-8")
    labels = _extract_response_draft_allowed_status_set(source)
    assert labels == {
        "REAL_CANDIDATE",
        "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL",
    }, (
        f"response_draft allowed set drift: got {sorted(labels)!r}. "
        "BLOCKED/PARTIAL/ASSET_INVENTORY_PASS/CONTRACT_ONLY 라벨에서 draft_text 노출 금지 — "
        "이전 비정본 라벨 부주의 잔존 위험을 차단."
    )
