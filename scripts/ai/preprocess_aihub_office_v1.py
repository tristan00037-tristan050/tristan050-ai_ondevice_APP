from __future__ import annotations
import argparse, json, re
from pathlib import Path
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ai._aihub_common_v1 import find_sample_files, sniff_records, try_get, normalize_text, build_row, jsonl_write, polite_present

def office_to_row(rec: dict, source_file: str) -> dict | None:
    # 오피스 데이터는 OCR 바운딩박스 구조라 rewrite 변환 불가.
    # plain_text가 200자 이상인 경우 summarize 태스크로 변환.
    plain_text = normalize_text(try_get(rec, "plain_text", "text", "content", "document", "input"))
    if not plain_text or len(plain_text) < 200:
        return None
    sentences = [s.strip() for s in re.split(r'[.\n]', plain_text) if len(s.strip()) > 10]
    if not sentences:
        return None
    completion = '. '.join(sentences[:2]) + '.'
    if len(completion) < 20:
        return None
    prompt = f"다음 문서를 3문장 이내로 요약하세요:\n{plain_text}"
    return build_row(prompt, completion, "summarize", "office", dataset_name="Office", source_file=source_file, record_id=f"office_{abs(hash(source_file+plain_text))%10**8:08d}", quality_flags=[])

def load_records(input_dir: str):
    rows = []
    for fp in find_sample_files(input_dir, limit=99999):
        fmt, recs = sniff_records(fp, sample_count=10**6)
        for rec in recs:
            row = office_to_row(rec, str(fp))
            if row:
                rows.append(row)
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--target", type=int, default=20000)
    args = ap.parse_args()
    rows = load_records(args.input_dir)[:args.target]
    count = jsonl_write(args.output, rows)
    print("AIHUB_OFFICE_LOAD_OK=1")
    print(f"AIHUB_OFFICE_COUNT={count}")

if __name__ == "__main__":
    main()
