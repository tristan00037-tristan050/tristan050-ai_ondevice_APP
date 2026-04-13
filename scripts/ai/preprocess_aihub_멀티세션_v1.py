from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, json
from pathlib import Path
from scripts.ai._aihub_common_v1 import build_row, write_jsonl

def generate_rows(input_dir: str):
    rows=[]
    for fp in sorted(Path(input_dir).rglob('*.json')):
        try: d=json.loads(fp.read_text(encoding='utf-8'))
        except Exception: continue
        for session in d.get('sessionInfo', []):
            dialog=session.get('dialog', [])
            for i in range(len(dialog)-1):
                p=str(dialog[i].get('utterance','')).strip(); c=str(dialog[i+1].get('utterance','')).strip()
                if p and c and len(p)>5 and len(c)>5:
                    rows.append(build_row(p, c, 'dialogue', 'aihub_멀티세션', '멀티세션', str(fp), f'multi_{len(rows):06d}'))
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input-dir', required=True); ap.add_argument('--output', required=True); ap.add_argument('--target', type=int, default=20000); args=ap.parse_args()
    rows=generate_rows(args.input_dir)[:args.target]
    write_jsonl(Path(args.output), rows)
    print('AIHUB_멀티세션_LOAD_OK=1'); print(f'AIHUB_멀티세션_COUNT={len(rows)}')
if __name__=='__main__': main()
