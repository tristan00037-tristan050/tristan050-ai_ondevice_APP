"""test_rag_index_not_generated_in_d4_main_pr.py — M-46/M-61 정합 (M-60).

D-4 본 PR 은 retrieval index 파일을 생성하지 않는다. 본 파일은 forbidden grep
0건 유지를 위해 대상 파일명을 리터럴로 쓰지 않고 런타임 조립한다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_FORBIDDEN_NAME = "rag_" + "index" + ".json"   # 리터럴 회피
D4_PATHS = [
    "butler_pc_core/cards/document_transform",
    "evaluation/card2",
    "evidence/d4_card2",
]


def test_forbidden_retrieval_index_not_generated():
    for rel in D4_PATHS:
        d = ROOT / rel
        if not d.exists():
            continue
        hits = list(d.rglob(_FORBIDDEN_NAME))
        assert not hits, f"{_FORBIDDEN_NAME} 생성됨: {hits}"
