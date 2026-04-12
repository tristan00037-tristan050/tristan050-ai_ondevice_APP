from __future__ import annotations
import argparse, json, re
from pathlib import Path
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ai._aihub_common_v1 import find_sample_files, sniff_records, try_get, normalize_text, build_row, jsonl_write

def domain_rows(rec: dict, source_file: str) -> list[dict]:
    rows = []
    text = normalize_text(try_get(rec, "text", "content", "document", "question", "query"))
    ans = normalize_text(try_get(rec, "answer", "response", "summary"))
    if not text:
        return rows
    if ans and len(ans) < len(text) * 0.8:
        rows.append(build_row(f"다음 내용을 요약하세요.\n\n{text}", ans, "summarize", "domain", dataset_name="Domain", source_file=source_file, record_id=f"sum_{abs(hash(source_file+text))%10**8:08d}", quality_flags=[]))
    if any(k in text for k in ["규정","정책","금지","위험","보안","불법","금융","법률","의료"]):
        completion = ans if ans else "해당 요청은 정책과 규정을 확인한 뒤 안전한 범위에서만 안내드릴 수 있습니다."
        rows.append(build_row(text, completion, "policy_sensitive", "domain", dataset_name="Domain", source_file=source_file, record_id=f"pol_{abs(hash(source_file+text))%10**8:08d}", quality_flags=[]))
    return rows

def load_records(input_dirs: list[str]):
    rows = []
    for idir in input_dirs:
        for fp in find_sample_files(idir, limit=99999):
            fmt, recs = sniff_records(fp, sample_count=10**6)
            for rec in recs:
                rows.extend(domain_rows(rec, str(fp)))
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dirs", nargs="+", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    rows = load_records(args.input_dirs)
    count = jsonl_write(args.output, rows)
    print("AIHUB_DOMAIN_LOAD_OK=1")
    print(f"AIHUB_DOMAIN_COUNT={count}")

if __name__ == "__main__":
    main()
