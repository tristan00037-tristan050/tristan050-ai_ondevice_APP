from __future__ import annotations
import argparse, json, random, sys
from pathlib import Path
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ai._aihub_common_v1 import find_sample_files, sniff_records, try_get, normalize_text, build_row, jsonl_write, tool_name_from_sql

_UTTERANCE_KEYS = ("utterance", "question", "nl", "nl_query")
_QUERY_KEYS = ("query", "sql", "sql_query", "query_sql", "label_sql", "answer")


def nl2sql_to_row(rec: dict, source_file: str) -> dict | None:
    natural_q = normalize_text(try_get(rec, *_UTTERANCE_KEYS))
    sql = normalize_text(try_get(rec, *_QUERY_KEYS))
    if not natural_q or not sql:
        return None
    if "{" in natural_q and '"tool_name"' in natural_q:
        return None
    completion = json.dumps({"tool_name": tool_name_from_sql(sql), "arguments": {"query": sql.strip()}}, ensure_ascii=False)
    return build_row(natural_q, completion, "tool_call", "nl2sql", dataset_name="NL2SQL", source_file=source_file, extraction_mode="nl2sql_structured", record_id=f"nl2sql_{abs(hash(source_file+natural_q))%10**8:08d}", quality_flags=[])


def _iter_nl2sql_recs(fp: Path):
    """{"Dataset":{}, "data":[...]} 구조 우선 시도, 실패 시 sniff_records로 fallback."""
    try:
        raw = json.loads(fp.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
            yield from raw["data"]
            return
    except Exception:
        pass
    _, recs = sniff_records(fp, sample_count=10**6)
    yield from recs


def load_records(input_dir: str):
    rows = []
    for fp in find_sample_files(input_dir, limit=99999):
        for rec in _iter_nl2sql_recs(fp):
            row = nl2sql_to_row(rec, str(fp))
            if row:
                rows.append(row)
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--target", type=int, default=30000)
    args = ap.parse_args()
    rows = load_records(args.input_dir)
    rows = rows[:args.target]
    count = jsonl_write(args.output, rows)
    print("AIHUB_NL2SQL_LOAD_OK=1")
    print(f"AIHUB_NL2SQL_COUNT={count}")

if __name__ == "__main__":
    main()
