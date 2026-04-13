from __future__ import annotations
import sys, re, json, zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from scripts.ai._aihub_common_v1 import build_row, write_jsonl

def generate_rows(input_dir: str):
    rows = []
    for zip_fp in sorted(Path(input_dir).rglob('TL*.zip')):
        try:
            z_obj = zipfile.ZipFile(zip_fp)
        except zipfile.BadZipFile:
            continue
        with z_obj as z:
            for tf_raw in z.namelist():
                if not tf_raw.endswith('.json'):
                    continue
                try:
                    with z.open(tf_raw) as f:
                        d = json.load(f)
                except Exception:
                    continue
                meta = d.get('meta', {})
                if meta.get('source_language') != 'ko':
                    continue
                sents = d.get('sents', [])
                texts = [s.get('source_cleaned','').strip() for s in sents if s.get('source_cleaned','').strip()]
                merged = ' '.join(texts)
                if len(merged) < 50:
                    continue
                prompt = f'다음 금융/법률 문서의 핵심 내용을 요약하세요:\n{merged[:600]}'
                sentences = [s.strip() for s in re.split(r'[.\n]', merged) if len(s.strip()) > 10]
                completion = '. '.join(sentences[:2]) + '.' if sentences else ''
                if len(completion) < 20:
                    continue
                rows.append(build_row(prompt, completion, 'policy_sensitive', 'aihub_금융', '금융', f'{zip_fp}/{tf_raw}', f'finance_{len(rows):06d}'))
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input-dir', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--target', type=int, default=10000)
    args = ap.parse_args()
    rows = generate_rows(args.input_dir)[:args.target]
    write_jsonl(Path(args.output), rows)
    print('AIHUB_금융_LOAD_OK=1')
    print(f'AIHUB_금융_COUNT={len(rows)}')

if __name__ == '__main__':
    main()
