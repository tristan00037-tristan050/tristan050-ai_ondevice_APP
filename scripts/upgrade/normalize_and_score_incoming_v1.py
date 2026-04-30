#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Iterable


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def normalize_row(row: dict, source: str) -> dict | None:
    prompt = str(row.get('prompt', '')).strip()
    completion = str(row.get('completion', '')).strip()
    if not prompt or not completion:
        return None
    function = str(row.get('function', 'dialogue')).strip() or 'dialogue'
    lang = str(row.get('lang', 'mixed')).strip() or 'mixed'
    quality = float(row.get('quality_score', 0.8))
    return {
        'prompt': prompt,
        'completion': completion,
        'function': function,
        'lang': lang,
        'source': source,
        'quality_score': quality,
        'prompt_digest_sha256': sha(prompt),
        'output_digest_sha256': sha(completion),
    }


def iter_jsonl(paths: Iterable[Path]):
    for p in paths:
        with p.open(encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                norm = normalize_row(row, p.name)
                if norm is not None:
                    yield norm


def main() -> None:
    ap = argparse.ArgumentParser(description='Normalize incoming supervised examples')
    ap.add_argument('--incoming-dir', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    incoming_dir = Path(args.incoming_dir)
    rows = list(iter_jsonl(sorted(incoming_dir.glob('*.jsonl'))))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'NORMALIZE_INCOMING_OK=1 rows={len(rows)}')


if __name__ == '__main__':
    main()
