"""build_wikipedia_index.py — D-4 Card 2 Wikipedia FTS5 보조 인덱스 생성.

2차 보조 검색 인덱스 (학습 아님, retrieval/eval 보조). 외부 송신 0.

정직 한계: 전체 Wikipedia 코퍼스는 수 GB 규모로 본 환경에서 수신 불가다.
본 스크립트는 (a) FTS5 스키마를 생성하고, (b) 코퍼스 경로(BUTLER_WIKI_CORPUS)가
주어지면 해당 코퍼스를, 없으면 slot_pattern_lexicon 의 슬롯 정의를 seed
문서로 색인한다. 실제 Wikipedia 색인은 코퍼스 보유 환경에서 재실행해야 한다.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "butler_pc_core/factpack/wikipedia_index.sqlite"
LEXICON = ROOT / "butler_pc_core/cards/document_transform/slot_pattern_lexicon.json"


def _seed_docs() -> list[tuple[str, str]]:
    """코퍼스 부재 시 lexicon 슬롯 정의를 seed 문서로 사용."""
    if not LEXICON.exists():
        return []
    doc = json.loads(LEXICON.read_text(encoding="utf-8"))
    return [(slot, " ".join(terms))
            for slot, terms in doc.get("lexicon", {}).items()]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    conn = sqlite3.connect(str(OUT))
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE wiki_fts USING fts5(title, body, tokenize='unicode61')"
        )
        corpus_path = os.environ.get("BUTLER_WIKI_CORPUS", "").strip()
        source = "wikipedia_corpus" if corpus_path and Path(corpus_path).exists() else "lexicon_seed"
        docs: list[tuple[str, str]] = []
        if source == "wikipedia_corpus":
            for line in Path(corpus_path).open(encoding="utf-8"):
                if line.strip():
                    rec = json.loads(line)
                    docs.append((rec.get("title", ""), rec.get("body", "")))
        else:
            docs = _seed_docs()
        conn.executemany("INSERT INTO wiki_fts(title, body) VALUES (?, ?)", docs)
        conn.commit()
        count = conn.execute("SELECT count(*) FROM wiki_fts").fetchone()[0]
    finally:
        conn.close()
    print(json.dumps({"out": str(OUT), "source": source, "doc_count": count,
                       "fts": "fts5"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
