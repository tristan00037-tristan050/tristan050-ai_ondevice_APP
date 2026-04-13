from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, json
from collections import Counter
from pathlib import Path
from scripts.ai._aihub_common_v1 import write_json, write_jsonl

def read_rows(fp: Path):
    if not fp.exists(): return []
    return [json.loads(l) for l in fp.read_text(encoding='utf-8').splitlines() if l.strip()]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input-dir', required=True); ap.add_argument('--output', required=True); args=ap.parse_args()
    inp=Path(args.input_dir)
    files=['tool_call_nl2sql.jsonl','rewrite_office.jsonl','retrieval_event.jsonl','dialogue_감성대화.jsonl','dialogue_공감형대화.jsonl','dialogue_멀티세션.jsonl','전문분야.jsonl','금융.jsonl','웹데이터.jsonl']
    input_files={}; source_counts=Counter(); function_counts=Counter(); split_counts=Counter(); all_rows=[]; seen=set(); dedup=0
    for name in files:
        rows=read_rows(inp/name)
        input_files[name]=len(rows)
        for r in rows:
            if r['prompt'] in seen: dedup += 1; continue
            seen.add(r['prompt']); all_rows.append(r)
            source_counts[r['source']]+=1; function_counts[r['function']]+=1; split_counts[r['split']]+=1
    write_jsonl(Path(args.output), all_rows)
    write_json(inp/'merge_manifest.json', {'input_files': input_files,'raw_line_count': sum(input_files.values()),'dedup_removed': dedup,'final_line_count': len(all_rows),'function_counts': dict(function_counts),'source_counts': dict(source_counts),'validation_split_counts': dict(split_counts)})
    print('AIHUB_MERGE_OK=1'); print(f'AIHUB_TOTAL_COUNT={len(all_rows)}')
if __name__=='__main__': main()
