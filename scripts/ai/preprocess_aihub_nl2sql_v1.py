from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse, json, zipfile
from pathlib import Path
from scripts.ai._aihub_common_v1 import build_row, safe_zip_members, write_jsonl

def tool_name_from_sql(sql: str) -> str:
    s=sql.strip().upper()
    if s.startswith('SELECT'): return 'db_query'
    if s.startswith('INSERT'): return 'db_insert'
    if s.startswith('UPDATE'): return 'db_update'
    if s.startswith('DELETE'): return 'db_delete'
    return 'db_execute'

def generate_rows(input_dir: str):
    rows=[]
    for zip_fp in sorted(Path(input_dir).rglob('*.zip')):
        try:
            z_obj = zipfile.ZipFile(zip_fp)
        except zipfile.BadZipFile:
            continue
        with z_obj as z:
            for tf_raw, jf in safe_zip_members(z):
                if not jf.endswith('.json'): continue
                with z.open(tf_raw) as f:
                    try: d=json.load(f)
                    except Exception: continue
                items=d.get('data', [])
                if isinstance(items, dict): items=[items]
                for item in items:
                    nl=next((str(item.get(k,'')).strip() for k in ('utterance','question','nl','nl_query') if str(item.get(k,'')).strip()), '')
                    sql=next((str(item.get(k,'')).strip() for k in ('query','sql','sql_query','query_sql','label_sql','answer') if str(item.get(k,'')).strip()), '')
                    if nl and sql:
                        comp=json.dumps({'tool_name': tool_name_from_sql(sql), 'arguments': {'query': sql}}, ensure_ascii=False)
                        rows.append(build_row(nl, comp, 'tool_call', 'aihub_nl2sql', 'NL2SQL', f'{zip_fp}/{jf}', f'nl2sql_{len(rows):06d}'))
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input-dir', required=True); ap.add_argument('--output', required=True); ap.add_argument('--target', type=int, default=30000); args=ap.parse_args()
    rows=generate_rows(args.input_dir)[:args.target]
    write_jsonl(Path(args.output), rows)
    print('AIHUB_NL2SQL_LOAD_OK=1'); print(f'AIHUB_NL2SQL_COUNT={len(rows)}')
if __name__=='__main__': main()
