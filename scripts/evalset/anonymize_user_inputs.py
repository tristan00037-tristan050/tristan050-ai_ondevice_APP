#!/usr/bin/env python3
"""anonymize_user_inputs.py — 단계 6.5.5 Day 1.

사용자 입력 텍스트를 21종 표준 토큰으로 익명화하여 EvalSet JSONL 로 변환.

- raw_text 저장 금지 (5종 금지 키 차단)
- text_redacted + raw_digest16 만 출력
- 11종 PATTERN 정규식 + 키워드 치환

사용:
    python3 scripts/evalset/anonymize_user_inputs.py \\
        --input /path/to/raw_lines.txt \\
        --out   /path/to/redacted.jsonl \\
        --source internal_log_redacted
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple


# ── 1. 정규식 PATTERN 11종 ────────────────────────────────────────────────
PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    # 이메일
    ("EMAIL",   re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    # 한국식 전화번호 (010-xxxx-xxxx, 02-xxxx-xxxx)
    ("PHONE",   re.compile(r"(?<!\d)0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}(?!\d)"), "[PHONE]"),
    # URL
    ("URL",     re.compile(r"https?://[A-Za-z0-9.\-_/?=&%#~+]+"), "[URL]"),
    # PR 번호 (PR #123 또는 #123 단독)
    ("PR",      re.compile(r"(?:PR\s*)?#\d{1,6}\b"), "[PR]"),
    # Git SHA (7~40자 16진수)
    ("COMMIT",  re.compile(r"\b[0-9a-f]{7,40}\b"), "[COMMIT]"),
    # POSIX/Windows 경로
    ("PATH",    re.compile(r"(?:/[A-Za-z0-9_.-]+){2,}|[A-Z]:\\\\[A-Za-z0-9_\\\\.-]+"), "[PATH]"),
    # 날짜 (YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD)
    ("DATE",    re.compile(r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b"), "[DATE]"),
    # 시각 (HH:MM 또는 HH시 MM분)
    ("TIME",    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b|\b\d{1,2}시(?:\s*\d{1,2}분)?"), "[TIME]"),
    # 서버 IP (IPv4)
    ("SERVER",  re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"), "[SERVER]"),
    # API key / token (sk_live_, AKIA..., ghp_...)
    ("SECRET",  re.compile(r"(?:sk[_-]live[_-][A-Za-z0-9]+|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36})"), "[SECRET]"),
    # 카드 번호 (4-4-4-4)
    ("CARD",    re.compile(r"(?<!\d)(?:\d{4}[- ]?){3}\d{4}(?!\d)"), "[CARD]"),
]


# ── 2. 키워드 치환 (정규식보다 단순 키워드가 맞는 경우) ────────────────────
KEYWORD_REPLACEMENTS: List[Tuple[str, str]] = [
    # Git 브랜치명 패턴 — feat/foo-bar, fix/abc-def 류
    (r"\b(?:feat|fix|chore|docs|refactor|test)/[a-zA-Z0-9_\-/]+", "[BRANCH]"),
]


# ── 3. 금지 키 5종 (출력 JSON 어디에도 포함 금지) ──────────────────────────
FORBIDDEN_KEYS = (
    "raw_text",
    "original_text",
    "plain_text",
    "user_text",
    "source_text",
)


# ── 4. digest16 함수 ──────────────────────────────────────────────────────
def digest16(raw: str) -> str:
    """sha256:<16 hex> — 원문 중복 방지용 (복원 불가)."""
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ── 5. 익명화 함수 ────────────────────────────────────────────────────────
def anonymize_line(raw: str) -> Tuple[str, List[str]]:
    """raw 입력 → (text_redacted, entities_replaced_list).

    entities_replaced_list 는 어떤 토큰으로 몇 번 치환됐는지 모니터링용.
    """
    text = raw
    replaced: List[str] = []

    # KEYWORD 우선 (BRANCH 가 PATH 보다 먼저)
    for pat, token in KEYWORD_REPLACEMENTS:
        compiled = re.compile(pat)
        n = len(compiled.findall(text))
        if n > 0:
            text = compiled.sub(token, text)
            replaced.extend([token] * n)

    # 정규식 PATTERN 순회 (앞 패턴이 우선 — SECRET 처럼 specific 한 것 먼저 두는 게 안전)
    for name, regex, token in PATTERNS:
        n = len(regex.findall(text))
        if n > 0:
            text = regex.sub(token, text)
            replaced.extend([token] * n)

    return text.strip(), replaced


def to_eval_item(raw: str, source: str, idx: int) -> dict:
    """raw → EvalSet JSON item (draft 상태, 라벨 미부여).

    금지 키 5종 (raw_text 등) 은 절대 포함 X.
    """
    text_redacted, entities = anonymize_line(raw)
    item = {
        "sample_id":               f"card1_{idx:06d}",
        "text_redacted":           text_redacted,
        "raw_digest16":            digest16(raw),
        "source":                  source,
        "consent_scope":           "evalset_intent_deadline",
        "intent_type":             "REQUEST",        # placeholder, 라벨링 단계에서 갱신
        "deadline_type":           "NONE",           # placeholder
        "deadline_is_actionable":  False,
        "slice_tags":              [],
        "risk_tags":               [],
        "action_required":         False,
        "answer_required":         False,
        "auto_apply_allowed":      False,
        "label_status":            "draft",
        "annotator_count":         0,
        "adjudicated":             False,
    }
    # FORBIDDEN_KEYS 절대 들어가지 않도록 검증
    for k in item.keys():
        if k in FORBIDDEN_KEYS:
            raise RuntimeError(f"forbidden key emitted: {k}")
    return item


# ── 6. CLI ────────────────────────────────────────────────────────────────
def iter_raw_lines(path: Path) -> Iterable[str]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if line.strip():
                yield line


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",  required=True, help="raw text input (one per line)")
    p.add_argument("--out",    required=True, help="output JSONL path")
    p.add_argument("--source", required=True,
                   choices=("synthetic_gold", "beta_log_redacted",
                            "internal_log_redacted", "adjudicated_boundary"))
    p.add_argument("--start-index", type=int, default=1)
    args = p.parse_args()

    in_path  = Path(args.input)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    entity_counts: dict = {}

    with out_path.open("w", encoding="utf-8") as out_f:
        for i, raw in enumerate(iter_raw_lines(in_path), start=args.start_index):
            item = to_eval_item(raw, args.source, i)
            out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
            total += 1
            _, ent = anonymize_line(raw)
            for token in ent:
                entity_counts[token] = entity_counts.get(token, 0) + 1

    report = {
        "ok": True,
        "total_items": total,
        "entities_replaced": entity_counts,
        "output": str(out_path),
        "source": args.source,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
