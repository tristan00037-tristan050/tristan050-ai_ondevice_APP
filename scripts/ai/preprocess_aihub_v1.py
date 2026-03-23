#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

VALID_FUNCTIONS = ("dialogue", "summarize", "retrieval_transform", "policy_sensitive")
VALID_SPLITS = ("train", "validation", "test")

PATH_HINTS = {
    "dialogue": ["일상대화", "대화", "dialogue", "conversation", "chat"],
    "summarize": ["문서요약", "요약", "summary", "summarize"],
    "retrieval_transform": ["기계독해", "질의응답", "독해", "reading", "qa", "qna", "mrc"],
    "policy_sensitive": ["법령", "판례", "컴플라이언스", "compliance", "policy", "regulation", "규정"],
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_lang(text: str) -> str:
    has_ko = bool(re.search(r"[가-힣]", text or ""))
    has_en = bool(re.search(r"[A-Za-z]", text or ""))
    if has_ko and has_en:
        return "mixed"
    if has_ko:
        return "ko"
    return "en"


def flatten_text(value: Any) -> str:
    chunks: list[str] = []
    def _walk(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, str):
            s = v.strip()
            if s:
                chunks.append(s)
            return
        if isinstance(v, list):
            for item in v:
                _walk(item)
            return
        if isinstance(v, dict):
            preferred = [
                "sentence", "sentence_text", "utterance", "text", "context", "content",
                "paragraph", "body", "title", "question", "answer", "instruction", "output"
            ]
            hit = False
            for key in preferred:
                if key in v:
                    hit = True
                    _walk(v.get(key))
            if not hit:
                for item in v.values():
                    _walk(item)
            return
        chunks.append(str(v).strip())
    _walk(value)
    joined = "\n".join([c for c in chunks if c])
    joined = re.sub(r"\n{3,}", "\n\n", joined).strip()
    return joined


def iter_json_objects(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from iter_json_objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_json_objects(item)


def path_hint(path: Path) -> str | None:
    lowered = "/".join(path.parts).lower()
    for fn, hints in PATH_HINTS.items():
        if any(h.lower() in lowered for h in hints):
            return fn
    return None


def detect_schemas(payload: Any) -> set[str]:
    found: set[str] = set()
    for obj in iter_json_objects(payload):
        if "documents" in obj and isinstance(obj.get("documents"), list):
            docs = obj.get("documents") or []
            if any(isinstance(d, dict) and ("abstractive" in d or "extractive" in d or "summary" in d) for d in docs):
                found.add("summarize")
        if isinstance(obj.get("body"), list) or isinstance(obj.get("dialog"), list):
            turns = obj.get("body") if isinstance(obj.get("body"), list) else obj.get("dialog")
            if turns and any(isinstance(t, dict) and ("utterance" in t or "text" in t) for t in turns):
                found.add("dialogue")
        if isinstance(obj.get("paragraphs"), list) and any(isinstance(p, dict) and ("qas" in p or "context" in p) for p in obj.get("paragraphs", [])):
            found.add("retrieval_transform")
        if isinstance(obj.get("data"), list):
            data = obj.get("data") or []
            if any(isinstance(d, dict) and isinstance(d.get("paragraphs"), list) for d in data):
                found.add("retrieval_transform")
        ann = obj.get("annotation")
        ann_alt = obj.get("annotaiton")
        if isinstance(ann, list) or isinstance(ann, dict) or isinstance(ann_alt, list) or isinstance(ann_alt, dict):
            ann_nodes = []
            for a in (ann, ann_alt):
                if isinstance(a, list):
                    ann_nodes.extend([x for x in a if isinstance(x, dict)])
                elif isinstance(a, dict):
                    ann_nodes.append(a)
            if any("QnA" in a for a in ann_nodes) or any("contents" in a for a in ann_nodes):
                found.add("policy_sensitive")
    return found


def normalize_row(prompt: str, completion: str, function: str, source: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = (prompt or "").strip()
    completion = (completion or "").strip()
    if not prompt or not completion:
        raise ValueError("EMPTY_PROMPT_OR_COMPLETION")
    row = {
        "prompt": prompt,
        "completion": completion,
        "function": function,
        "lang": detect_lang(prompt + "\n" + completion),
        "format": "qwen2.5_chat",
        "source": source,
        "prompt_digest_sha256": sha256_text(prompt),
        "output_digest_sha256": sha256_text(completion),
    }
    if meta:
        row["meta"] = meta
    return row


def parse_summarize(payload: Any, source: str) -> Iterator[dict[str, Any]]:
    for obj in iter_json_objects(payload):
        docs = obj.get("documents")
        if not isinstance(docs, list):
            continue
        for idx, doc in enumerate(docs):
            if not isinstance(doc, dict):
                continue
            body = flatten_text(doc.get("text") or doc.get("content") or doc.get("document") or doc)
            summaries = doc.get("abstractive") or doc.get("extractive") or doc.get("summary") or []
            if isinstance(summaries, str):
                summaries = [summaries]
            title = (doc.get("title") or "").strip()
            summary_text = next((str(x).strip() for x in summaries if str(x).strip()), "")
            if not body or not summary_text:
                continue
            prompt = f"다음 문서를 요약하세요.\n제목: {title}\n본문:\n{body}".strip()
            yield normalize_row(prompt, summary_text, "summarize", source, {"doc_index": idx, "title": title})


def parse_dialogue(payload: Any, source: str) -> Iterator[dict[str, Any]]:
    seen_conv = 0
    for obj in iter_json_objects(payload):
        turns = None
        if isinstance(obj.get("body"), list):
            turns = obj.get("body")
        elif isinstance(obj.get("dialog"), list):
            turns = obj.get("dialog")
        if not turns or not isinstance(turns, list):
            continue
        utterances = []
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            utt = (turn.get("utterance") or turn.get("text") or turn.get("sentence") or "").strip()
            if not utt:
                continue
            speaker = (turn.get("speaker") or turn.get("participantID") or turn.get("participant_id") or turn.get("speaker_id") or "speaker").strip()
            utterances.append((speaker, utt))
        if len(utterances) < 2:
            continue
        seen_conv += 1
        for idx in range(1, len(utterances)):
            history = utterances[:idx]
            next_speaker, next_utt = utterances[idx]
            history_text = "\n".join(f"{spk}: {utt}" for spk, utt in history)
            prompt = f"다음 대화를 이어서 자연스럽게 답하세요.\n{history_text}\n{next_speaker}:".strip()
            yield normalize_row(prompt, next_utt, "dialogue", source, {"conversation_index": seen_conv, "turn_index": idx})


def iter_squad_like_nodes(payload: Any) -> Iterator[tuple[str, list[dict[str, Any]], dict[str, Any]]]:
    # direct paragraphs style
    for obj in iter_json_objects(payload):
        paragraphs = obj.get("paragraphs")
        if isinstance(paragraphs, list):
            base_meta = {k: obj.get(k) for k in ("title", "agency", "time") if k in obj}
            for para in paragraphs:
                if not isinstance(para, dict):
                    continue
                context = flatten_text(para.get("context") or para.get("paragraph") or para.get("content"))
                qas = para.get("qas") or para.get("QnA") or []
                if context and isinstance(qas, list):
                    yield context, qas, base_meta
    # top-level data list style
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        for item in payload.get("data"):
            if not isinstance(item, dict):
                continue
            paragraphs = item.get("paragraphs")
            if not isinstance(paragraphs, list):
                continue
            base_meta = {k: item.get(k) for k in ("title", "agency", "time") if k in item}
            for para in paragraphs:
                if not isinstance(para, dict):
                    continue
                context = flatten_text(para.get("context") or para.get("paragraph") or para.get("content"))
                qas = para.get("qas") or []
                if context and isinstance(qas, list):
                    yield context, qas, base_meta


def parse_retrieval_transform(payload: Any, source: str) -> Iterator[dict[str, Any]]:
    for context, qas, meta in iter_squad_like_nodes(payload):
        for qa in qas:
            if not isinstance(qa, dict):
                continue
            question = (qa.get("question") or qa.get("instruction") or "").strip()
            if not question:
                continue
            answer_text = ""
            answers = qa.get("answers")
            answer_obj = qa.get("answer")
            if isinstance(answers, list):
                for ans in answers:
                    if isinstance(ans, dict) and str(ans.get("text", "")).strip():
                        answer_text = str(ans.get("text", "")).strip()
                        break
                    if isinstance(ans, str) and ans.strip():
                        answer_text = ans.strip()
                        break
            elif isinstance(answer_obj, dict):
                answer_text = str(answer_obj.get("text", "")).strip()
            if not answer_text and qa.get("is_impossible") is True:
                answer_text = "정답 없음"
            if not answer_text:
                continue
            prompt = f"다음 지문을 읽고 질문에 답하세요.\n지문:\n{context}\n질문: {question}".strip()
            meta_out = dict(meta)
            meta_out.update({"qa_id": qa.get("id") or qa.get("question_id")})
            yield normalize_row(prompt, answer_text, "retrieval_transform", source, meta_out)


def iter_annotation_nodes(payload: Any) -> Iterator[dict[str, Any]]:
    for obj in iter_json_objects(payload):
        for key in ("annotation", "annotaiton"):
            val = obj.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        yield item
            elif isinstance(val, dict):
                yield val


def parse_policy_sensitive(payload: Any, source: str) -> Iterator[dict[str, Any]]:
    for ann in iter_annotation_nodes(payload):
        title = (ann.get("contents_title") or ann.get("title") or "").strip()
        qna = ann.get("QnA")
        if isinstance(qna, list):
            for item in qna:
                if not isinstance(item, dict):
                    continue
                instruction = (item.get("instruction") or item.get("question") or "").strip()
                options = (item.get("input") or "").strip()
                output = (item.get("output") or item.get("answer") or "").strip()
                if not instruction or not output:
                    continue
                prompt = f"다음 법령/컴플라이언스 질의에 답하세요.\n제목: {title}\n질의: {instruction}"
                if options:
                    prompt += f"\n보기: {options}"
                meta = {
                    "question_id": item.get("question_id"),
                    "role": item.get("role"),
                    "question_type": item.get("question_type"),
                    "contents_title": title,
                }
                yield normalize_row(prompt, output, "policy_sensitive", source, meta)
        contents = ann.get("contents")
        if isinstance(contents, list):
            for block in contents:
                if not isinstance(block, dict):
                    continue
                sentence_text = (block.get("sentence_text") or block.get("text") or "").strip()
                sentence_class = (block.get("sentence_class") or block.get("label") or "").strip()
                if not sentence_text or not sentence_class:
                    continue
                prompt = f"다음 문장을 컴플라이언스 관점에서 분류하세요.\n제목: {title}\n문장: {sentence_text}".strip()
                yield normalize_row(prompt, sentence_class, "policy_sensitive", source, {
                    "sentence_id": block.get("sentence_id"),
                    "contents_title": title,
                })


def choose_parser(payload: Any, path: Path) -> str | None:
    hinted = path_hint(path)
    found = detect_schemas(payload)
    if hinted and hinted in found:
        return hinted
    if hinted and not found:
        return hinted
    if len(found) == 1:
        return next(iter(found))
    priority = ("summarize", "dialogue", "retrieval_transform", "policy_sensitive")
    for fn in priority:
        if fn in found:
            return fn
    return None


def parse_file(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    parser_name = choose_parser(payload, path)
    if parser_name == "summarize":
        return list(parse_summarize(payload, path.as_posix())), parser_name
    if parser_name == "dialogue":
        return list(parse_dialogue(payload, path.as_posix())), parser_name
    if parser_name == "retrieval_transform":
        return list(parse_retrieval_transform(payload, path.as_posix())), parser_name
    if parser_name == "policy_sensitive":
        return list(parse_policy_sensitive(payload, path.as_posix())), parser_name
    return [], None


def split_rows(rows: list[dict[str, Any]], seed: int) -> dict[str, list[dict[str, Any]]]:
    random.Random(seed).shuffle(rows)
    total = len(rows)
    train_n = max(1, int(total * 0.8)) if total >= 1 else 0
    val_n = max(1, int(total * 0.1)) if total >= 3 else (1 if total == 2 else 0)
    if train_n + val_n > total:
        val_n = max(0, total - train_n)
    test_n = max(0, total - train_n - val_n)
    train = rows[:train_n]
    val = rows[train_n:train_n + val_n]
    test = rows[train_n + val_n:train_n + val_n + test_n]
    return {"train": train, "validation": val, "test": test}


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]], split_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            row2 = dict(row)
            row2["split"] = split_name
            f.write(json.dumps(row2, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Hub preprocessing v1")
    ap.add_argument("--root-dir", required=True, help="AI Hub dataset root directory")
    ap.add_argument("--out-dir", required=True, help="Output directory for JSONL splits")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit-files", type=int, default=0)
    ap.add_argument("--strict", action="store_true", help="Fail when unknown JSON structure is found")
    args = ap.parse_args()

    root_dir = Path(args.root_dir)
    out_dir = Path(args.out_dir)
    files = sorted(root_dir.rglob("*.json"))
    if args.limit_files > 0:
        files = files[: args.limit_files]

    all_rows: list[dict[str, Any]] = []
    seen = set()
    stats = {
        "files_total": len(files),
        "files_parsed": 0,
        "files_skipped": 0,
        "rows_total": 0,
        "dedup_removed": 0,
        "parser_counts": Counter(),
        "function_counts": Counter(),
        "errors": [],
    }

    for path in files:
        try:
            rows, parser_name = parse_file(path)
        except Exception as e:
            stats["files_skipped"] += 1
            stats["errors"].append({"file": str(path), "error": f"{type(e).__name__}: {e}"})
            continue
        if parser_name is None:
            stats["files_skipped"] += 1
            if args.strict:
                stats["errors"].append({"file": str(path), "error": "UNKNOWN_JSON_STRUCTURE"})
            continue
        stats["files_parsed"] += 1
        stats["parser_counts"][parser_name] += 1
        for row in rows:
            digest = row["prompt_digest_sha256"] + ":" + row["output_digest_sha256"]
            if digest in seen:
                stats["dedup_removed"] += 1
                continue
            seen.add(digest)
            all_rows.append(row)
            stats["function_counts"][row["function"]] += 1

    stats["rows_total"] = len(all_rows)
    if len(all_rows) == 0:
        summary = {
            "AIHUB_LOAD_OK": 0,
            "mode": "aihub_preprocess_v1",
            "root_dir": str(root_dir),
            "out_dir": str(out_dir),
            "stats": stats,
            "reason": "NO_ROWS_AFTER_PARSE",
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("AIHUB_LOAD_OK=0")
        sys.exit(1)

    splits = split_rows(all_rows, args.seed)
    for split_name in VALID_SPLITS:
        write_jsonl(out_dir / f"{split_name}.jsonl", splits[split_name], split_name)

    summary = {
        "AIHUB_LOAD_OK": 1,
        "mode": "aihub_preprocess_v1",
        "root_dir": str(root_dir),
        "out_dir": str(out_dir),
        "stats": {
            **stats,
            "parser_counts": dict(stats["parser_counts"]),
            "function_counts": dict(stats["function_counts"]),
        },
        "split_counts": {k: len(v) for k, v in splits.items()},
        "detected_functions": sorted(dict(stats["function_counts"]).keys()),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("AIHUB_LOAD_OK=1")
    print(json.dumps(summary["split_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
