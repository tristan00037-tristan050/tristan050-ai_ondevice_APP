from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, csv, io, zipfile
from collections import defaultdict
from pathlib import Path
from scripts.ai._aihub_common_v1 import build_row, safe_zip_members, write_jsonl

def generate_rows(input_dir: str):
    rows=[]
    for zip_fp in sorted(Path(input_dir).rglob('*.zip')):
        try:
            z_obj = zipfile.ZipFile(zip_fp)
        except zipfile.BadZipFile:
            continue
        with z_obj as z:
            for tf in safe_zip_members(z):
                if not tf.endswith('.tsv'): continue
                with z.open(tf) as f:
                    content=f.read().decode('utf-8', errors='ignore')
                reader=csv.DictReader(io.StringIO(content), delimiter='	'); groups=defaultdict(list)
                for row in reader: groups[row.get('id','')].append(row)
                for gid, vals in groups.items():
                    speakers=[r for r in vals if r.get('utterance_type')=='0']; listeners=[r for r in vals if r.get('utterance_type')=='1']
                    for sp,ls in zip(speakers,listeners):
                        p=sp.get('utterance_text','').strip(); c=ls.get('utterance_text','').strip()
                        if p and c: rows.append(build_row(p, c, 'dialogue', 'aihub_공감형대화', '공감형대화', f'{zip_fp}/{tf}', f'empathy_{len(rows):06d}'))
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input-dir', required=True); ap.add_argument('--output', required=True); ap.add_argument('--target', type=int, default=20000); args=ap.parse_args()
    rows=generate_rows(args.input_dir)[:args.target]
    write_jsonl(Path(args.output), rows)
    print('AIHUB_공감형대화_LOAD_OK=1'); print(f'AIHUB_공감형대화_COUNT={len(rows)}')
if __name__=='__main__': main()
