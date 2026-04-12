from __future__ import annotations
import argparse, json
from pathlib import Path
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ai._aihub_common_v1 import find_sample_files, sniff_records, try_get, normalize_text, build_row, jsonl_write, polite_present

def office_to_row(rec: dict, source_file: str) -> dict | None:
    src = normalize_text(try_get(rec, "source_text", "input", "original", "content", "document"))
    tgt = normalize_text(try_get(rec, "target_text", "output", "generated", "answer", "rewritten"))
    if not src or not tgt:
        return None
    prompt = f"다음 문장을 고객 친화적이고 공손한 톤으로 다시 써주세요:\n{src}"
    keywords = [w for w in ["배송","결제","서비스","가격","약관","점검","반품","계정","혜택","주문","예약","보안","환불"] if w in src]
    return build_row(prompt, tgt, "rewrite", "office", dataset_name="Office", source_file=source_file, record_id=f"office_{abs(hash(source_file+src))%10**8:08d}", preserve_keywords=keywords, quality_flags=[])

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
