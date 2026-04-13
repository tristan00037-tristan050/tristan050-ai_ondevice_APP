from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, json, zipfile
from pathlib import Path
from scripts.ai._aihub_common_v1 import build_row, safe_zip_members, write_jsonl

def generate_rows(input_dir: str):
    rows=[]
    for zip_fp in sorted(Path(input_dir).rglob('*.zip')):
        with zipfile.ZipFile(zip_fp) as z:
            for jf in safe_zip_members(z):
                if not jf.endswith('.json'): continue
                with z.open(jf) as f:
                    try: obj=json.load(f)
                    except Exception: continue
                items=obj if isinstance(obj, list) else [obj]
                for item in items:
                    content=item.get('talk',{}).get('content',{})
                    hs=sorted(k for k in content if k.startswith('HS')); ss=sorted(k for k in content if k.startswith('SS'))
                    for hk,sk in zip(hs,ss):
                        p=str(content.get(hk,'')).strip(); c=str(content.get(sk,'')).strip()
                        if p and c: rows.append(build_row(p, c, 'dialogue', 'aihub_감성대화', '감성대화', f'{zip_fp}/{jf}', f'emotion_{len(rows):06d}'))
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input-dir', required=True); ap.add_argument('--output', required=True); ap.add_argument('--target', type=int, default=30000); args=ap.parse_args()
    rows=generate_rows(args.input_dir)[:args.target]
    write_jsonl(Path(args.output), rows)
    print('AIHUB_감성대화_LOAD_OK=1'); print(f'AIHUB_감성대화_COUNT={len(rows)}')
if __name__=='__main__': main()
