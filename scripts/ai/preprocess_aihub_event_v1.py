from __future__ import annotations
import argparse, json
from pathlib import Path
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ai._aihub_common_v1 import find_sample_files, sniff_records, try_get, normalize_text, build_row, jsonl_write, extract_event_fields

def event_to_row(rec: dict, source_file: str) -> dict | None:
    text = normalize_text(try_get(rec, "text", "content", "document", "context", "input"))
    if not text:
        return None
    fields = extract_event_fields(text)
    keys = ["이벤트","일시","장소"]
    completion = "\n".join([f"{k}: {fields.get(k,'')}" for k in ["이벤트","일시","장소","참여자","주최"] if fields.get(k)])
    if not completion:
        return None
    prompt = f"다음 원문을 지정 포맷으로 변환하세요.\n형식: 이벤트:/일시:/장소:/참여자:/주최:\n\n{text}"
    return build_row(prompt, completion, "retrieval_transform", "event", dataset_name="Event", source_file=source_file, record_id=f"event_{abs(hash(source_file+text))%10**8:08d}", output_keys=[k for k in ["이벤트","일시","장소","참여자","주최"] if fields.get(k)], quality_flags=[])

def load_records(input_dir: str):
    from pathlib import Path
    import json as _json
    import ast

    for fp in Path(input_dir).rglob("*.json"):
        try:
            with open(fp, encoding="utf-8") as f:
                d = _json.load(f)
            data = d.get("data", {})
            if not isinstance(data, dict):
                continue
            text = data.get("text", "").strip()
            events = data.get("event", [])
            if isinstance(events, str):
                try:
                    events = ast.literal_eval(events)
                except Exception:
                    continue
            if not text or not events:
                continue
            sentences = [
                e.get("sentence", "").strip()
                for e in events
                if isinstance(e, dict) and e.get("sentence", "").strip()
            ]
            if not sentences:
                continue
            lines = [f"이벤트 {i+1}: {s}" for i, s in enumerate(sentences[:3])]
            completion = "\n".join(lines)
            prompt = f"다음 기사에서 주요 이벤트를 추출하세요.\n\n기사: {text[:500]}"
            yield build_row(
                prompt, completion, "retrieval_transform", "event",
                dataset_name="Event", source_file=str(fp),
                record_id=f"event_{abs(hash(str(fp))) % 10**8:08d}",
                quality_flags=[],
            )
        except Exception:
            continue

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--target", type=int, default=30000)
    args = ap.parse_args()
    rows = list(load_records(args.input_dir))[:args.target]
    count = jsonl_write(args.output, rows)
    print("AIHUB_EVENT_LOAD_OK=1")
    print(f"AIHUB_EVENT_COUNT={count}")

if __name__ == "__main__":
    main()
