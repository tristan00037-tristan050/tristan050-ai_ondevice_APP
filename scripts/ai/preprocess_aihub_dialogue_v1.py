from __future__ import annotations
import argparse, json
from pathlib import Path
if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ai._aihub_common_v1 import find_sample_files, sniff_records, try_get, normalize_text, build_row, jsonl_write

def recs_from_dialogue_record(rec: dict, source_file: str) -> list[dict]:
    rows = []
    turns = rec.get("turns") or rec.get("dialogue") or rec.get("utterances")
    if isinstance(turns, list) and len(turns) >= 2:
        for a, b in zip(turns[:-1], turns[1:]):
            ua = normalize_text(try_get(a if isinstance(a,dict) else {"text":a}, "text", "utterance", "content"))
            ub = normalize_text(try_get(b if isinstance(b,dict) else {"text":b}, "text", "utterance", "content"))
            if ua and ub:
                rows.append(build_row(ua, ub, "dialogue", "dialogue", dataset_name="Dialogue", source_file=source_file, record_id=f"dlg_{abs(hash(source_file+ua+ub))%10**8:08d}", quality_flags=[]))
        return rows
    prompt = normalize_text(try_get(rec, "user", "query", "question", "utterance"))
    completion = normalize_text(try_get(rec, "assistant", "response", "answer", "reply"))
    if prompt and completion:
        rows.append(build_row(prompt, completion, "dialogue", "dialogue", dataset_name="Dialogue", source_file=source_file, record_id=f"dlg_{abs(hash(source_file+prompt+completion))%10**8:08d}", quality_flags=[]))
    return rows

def load_records(input_dirs: list[str]):
    rows = []
    for idir in input_dirs:
        for fp in find_sample_files(idir, limit=99999):
            fmt, recs = sniff_records(fp, sample_count=10**6)
            for rec in recs:
                rows.extend(recs_from_dialogue_record(rec, str(fp)))
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dirs", nargs="+", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    rows = load_records(args.input_dirs)
    count = jsonl_write(args.output, rows)
    print("AIHUB_DIALOGUE_LOAD_OK=1")
    print(f"AIHUB_DIALOGUE_COUNT={count}")

if __name__ == "__main__":
    main()
