#!/usr/bin/env python3
"""
preprocess_aihub_v1.py — AI Hub 데이터 → 버틀러 JSONL 변환

실행:
  python3 scripts/ai/preprocess_aihub_v1.py
  python3 scripts/ai/preprocess_aihub_v1.py \\
      --ssd-dir "/Volumes/T7 Shield/버틀러 트레이닝 데이터" \\
      --out-dir data/raw/aihub

폴더 → function 매핑:
  일상대화/     (또는 E1_일상대화/)       → dialogue
  문서요약/     (또는 E2_문서요약/)       → summarize
  질의응답/     (또는 E3_질의응답_기계독해/) → retrieval_transform
  질의응답/법령_판례/ (또는 E3_.../L_법령_판례/) → policy_sensitive

출력 포맷 (한 줄 JSON):
  {"prompt": "...", "completion": "...", "function": "dialogue",
   "split": "train", "source": "aihub"}

완료 기준:
  AIHUB_LOAD_OK=1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterator


# ── 폴더명 → function 매핑 ──────────────────────────────────────────────────
# 상위 폴더 이름(소문자, 정규화) 기준으로 매핑
# 순서 중요: 더 구체적인 경로(법령_판례)를 먼저 확인
_FOLDER_FUNCTION: list[tuple[str, str]] = [
    # policy_sensitive — 법령/판례 하위
    ("법령_판례",        "policy_sensitive"),
    ("l_법령_판례",      "policy_sensitive"),
    # dialogue
    ("일상대화",         "dialogue"),
    ("e1_일상대화",      "dialogue"),
    # summarize
    ("문서요약",         "summarize"),
    ("e2_문서요약",      "summarize"),
    # retrieval_transform
    ("질의응답",         "retrieval_transform"),
    ("e3_질의응답",      "retrieval_transform"),
    ("e3_질의응답_기계독해", "retrieval_transform"),
]

def _infer_function(file_path: Path, ssd_dir: Path) -> str:
    """파일 경로에서 function 분류 결정 (더 구체적인 매핑 우선)."""
    try:
        rel = file_path.relative_to(ssd_dir)
    except ValueError:
        return "retrieval_transform"

    parts_lower = [p.lower() for p in rel.parts]

    for keyword, func in _FOLDER_FUNCTION:
        if any(keyword in part for part in parts_lower):
            return func
    return "retrieval_transform"


# ── AI Hub JSON 파싱 — 다양한 스키마 지원 ────────────────────────────────────

def _iter_dialogue(data: object) -> Iterator[tuple[str, str]]:
    """대화 데이터: utterance 배열에서 인접 발화쌍 추출."""
    items = data if isinstance(data, list) else []
    if isinstance(data, dict):
        items = (data.get("data") or data.get("dataset") or
                 data.get("dialogs") or data.get("conversations") or [])

    for item in items:
        if not isinstance(item, dict):
            continue
        body = item.get("body") or item
        utters = (body.get("dialogue") or body.get("utterances") or
                  body.get("conversation") or [])
        if not isinstance(utters, list) or len(utters) < 2:
            continue
        for i in range(len(utters) - 1):
            u = utters[i]
            v = utters[i + 1]
            q = u.get("utterance") or u.get("text") or u.get("utter") or ""
            a = v.get("utterance") or v.get("text") or v.get("utter") or ""
            if q and a:
                yield q.strip(), a.strip()


def _iter_summary(data: object) -> Iterator[tuple[str, str]]:
    """요약 데이터: 원문 → 요약문 쌍 추출."""
    items = data if isinstance(data, list) else []
    if isinstance(data, dict):
        items = (data.get("data") or data.get("documents") or
                 data.get("dataset") or [])

    for item in items:
        if not isinstance(item, dict):
            continue
        body = item.get("body") or item

        # 원문 후보
        article = (body.get("article") or body.get("text") or
                   body.get("original_text") or body.get("content") or
                   body.get("passage") or "")
        # 요약문 후보
        summary = (body.get("summary") or body.get("abstractive") or
                   body.get("abstractiveText") or body.get("highlights") or "")

        # 리스트 형태 요약 처리
        if isinstance(summary, list):
            summary = " ".join(str(s) for s in summary)

        article = str(article).strip()
        summary = str(summary).strip()

        if len(article) >= 30 and len(summary) >= 10:
            prompt = f"다음 내용을 요약해 주세요:\n{article[:500]}"
            yield prompt, summary


def _iter_qa(data: object) -> Iterator[tuple[str, str]]:
    """질의응답/기계독해 데이터: question → answer 쌍 추출."""
    items = data if isinstance(data, list) else []
    if isinstance(data, dict):
        items = (data.get("data") or data.get("dataset") or
                 data.get("paragraphs") or [])

    for item in items:
        if not isinstance(item, dict):
            continue

        # LLM Instruction Tuning 형식
        instruction = item.get("instruction") or item.get("input") or ""
        output = item.get("output") or item.get("answer") or ""
        if instruction and output:
            yield str(instruction).strip(), str(output).strip()
            continue

        # 기계독해 형식 (SQuAD-like)
        body = item.get("body") or item
        paragraphs = body.get("paragraphs") or [body]
        for para in paragraphs:
            if not isinstance(para, dict):
                continue
            context = para.get("context") or para.get("passage") or ""
            qas = para.get("qas") or []
            for qa in qas:
                if not isinstance(qa, dict):
                    continue
                q = qa.get("question") or qa.get("query") or ""
                answers = qa.get("answers") or []
                if isinstance(answers, list) and answers:
                    a = answers[0].get("text") or answers[0].get("answer") or ""
                elif isinstance(answers, str):
                    a = answers
                else:
                    a = ""
                if q and a:
                    yield str(q).strip(), str(a).strip()


def _iter_policy(data: object) -> Iterator[tuple[str, str]]:
    """법령/판례 데이터: 법령 기반 QA 또는 텍스트 분석 쌍 추출."""
    # policy_sensitive는 QA 파싱과 동일하게 처리
    yield from _iter_qa(data)

    # 추가: 법령 원문 → 요약 쌍
    items = data if isinstance(data, list) else []
    if isinstance(data, dict):
        items = (data.get("data") or data.get("dataset") or [])

    for item in items:
        if not isinstance(item, dict):
            continue
        body = item.get("body") or item
        title = body.get("title") or body.get("law_name") or ""
        content = (body.get("content") or body.get("text") or
                   body.get("body_text") or "")
        summary = body.get("summary") or body.get("abstract") or ""

        if title and content and not summary:
            summary = content[:200].strip()
        if title and summary and len(summary) >= 20:
            prompt = f"다음 법령/판례 내용을 설명해 주세요: {title}"
            yield prompt, str(summary).strip()


_FUNCTION_PARSER = {
    "dialogue":             _iter_dialogue,
    "summarize":            _iter_summary,
    "retrieval_transform":  _iter_qa,
    "policy_sensitive":     _iter_policy,
}


# ── JSONL / JSON 파일 파싱 ──────────────────────────────────────────────────

def _load_json_file(path: Path) -> object:
    """JSON 또는 JSONL 파일 로드. 실패 시 None 반환 (fail-soft)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    text = text.strip()
    if not text:
        return None

    # JSONL 시도 (첫 줄이 { 또는 [ 로 시작)
    if text.startswith("{"):
        lines = [l for l in text.splitlines() if l.strip()]
        if len(lines) > 1:
            records = []
            for line in lines:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
            if records:
                return records

    try:
        return json.loads(text)
    except Exception:
        return None


def _process_folder(
    folder: Path,
    function: str,
    ssd_dir: Path,
) -> list[dict]:
    """폴더 내 JSON/JSONL 파일을 재귀 스캔하여 버틀러 레코드 추출."""
    results: list[dict] = []
    parser = _FUNCTION_PARSER.get(function, _iter_qa)
    seen_prompts: set[str] = set()

    json_files = sorted(
        list(folder.rglob("*.json")) + list(folder.rglob("*.jsonl"))
    )

    for jf in json_files:
        if jf.name.startswith("._"):
            continue

        # 파일 내 실제 function 재결정 (법령_판례 하위 파일 등)
        actual_func = _infer_function(jf, ssd_dir)
        actual_parser = _FUNCTION_PARSER.get(actual_func, parser)

        data = _load_json_file(jf)
        if data is None:
            continue

        try:
            for prompt, completion in actual_parser(data):
                prompt = prompt.strip()
                completion = completion.strip()
                if not prompt or not completion:
                    continue
                if len(prompt) < 5 or len(completion) < 5:
                    continue
                if prompt in seen_prompts:
                    continue
                seen_prompts.add(prompt)
                results.append({
                    "prompt": prompt,
                    "completion": completion,
                    "function": actual_func,
                    "split": "train",
                    "source": "aihub",
                })
        except Exception:
            continue  # fail-soft: 파일 단위 파싱 실패 건너뜀

    return results


# ── 메인 ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="AI Hub 데이터 → 버틀러 JSONL 변환")
    ap.add_argument(
        "--ssd-dir",
        default="/Volumes/T7 Shield/버틀러 트레이닝 데이터",
        help="SSD 루트 경로 (기본: /Volumes/T7 Shield/버틀러 트레이닝 데이터)",
    )
    ap.add_argument(
        "--out-dir",
        default="data/raw/aihub",
        help="출력 디렉토리 (기본: data/raw/aihub)",
    )
    args = ap.parse_args()

    ssd_dir = Path(args.ssd_dir)
    out_dir = Path(args.out_dir)

    if not ssd_dir.exists():
        print(f"BLOCK: SSD_DIR_NOT_FOUND:{ssd_dir}", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    # 폴더명 → function 매핑 (실제 SSD 폴더 기준)
    folder_map: list[tuple[Path, str]] = [
        (ssd_dir / "일상대화",       "dialogue"),
        (ssd_dir / "문서요약",       "summarize"),
        (ssd_dir / "질의응답",       "retrieval_transform"),
        # E1/E2/E3 패턴도 지원
        (ssd_dir / "E1_일상대화",    "dialogue"),
        (ssd_dir / "E2_문서요약",    "summarize"),
        (ssd_dir / "E3_질의응답_기계독해", "retrieval_transform"),
    ]

    total = 0
    function_counts: dict[str, int] = {}

    for folder, function in folder_map:
        if not folder.exists():
            continue

        print(f"  📂 {folder.name} → function={function} 처리 중...")
        records = _process_folder(folder, function, ssd_dir)

        if not records:
            print(f"     ⚠️  JSON 파일 없음 또는 파싱 결과 0건 (데이터 다운로드 필요)")
            continue

        out_file = out_dir / f"aihub_{function}.jsonl"
        with out_file.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        count = len(records)
        function_counts[function] = function_counts.get(function, 0) + count
        total += count
        print(f"     ✅ {count:,} 건 저장: {out_file}")

    # 결과 요약
    print("")
    print("── 변환 결과 요약 ──────────────────────")
    for func, cnt in sorted(function_counts.items()):
        print(f"  {func:<25} {cnt:>6} 건")
    print(f"  {'합계':<25} {total:>6} 건")
    print("")

    if total == 0:
        print(
            "  ℹ️  변환 결과 0건 — AI Hub 데이터가 아직 다운로드되지 않았을 수 있습니다.",
            file=sys.stderr,
        )
        print(
            "     SSD의 aihubshell 스크립트로 데이터를 먼저 다운로드해 주세요.",
            file=sys.stderr,
        )
        print(f"AIHUB_LOAD_OK=0")
        sys.exit(0)  # 데이터 미존재는 스크립트 오류가 아님

    print(f"AIHUB_LOAD_OK=1")
    print(f"AIHUB_TOTAL_RECORDS={total}")


if __name__ == "__main__":
    main()
