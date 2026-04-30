#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, random
from pathlib import Path

def load_jsonl(path: Path):
    rows=[]
    if not path.exists():
        return rows
    with path.open(encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def dedupe(rows: list[dict]) -> list[dict]:
    seen=set(); out=[]
    for r in rows:
        d=r.get('prompt_digest_sha256')
        if not d or d in seen:
            continue
        seen.add(d); out.append(r)
    return out

def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False)+'\n')

def main() -> None:
    ap = argparse.ArgumentParser(description='Build train/validation/test splits without prompt leakage')
    ap.add_argument('--primary', required=True)
    ap.add_argument('--secondary')
    ap.add_argument('--out-dir', required=True)
    args = ap.parse_args()
    random.seed(42)
    rows = load_jsonl(Path(args.primary))
    if args.secondary:
        rows.extend(load_jsonl(Path(args.secondary)))
    rows = dedupe(rows)
    random.shuffle(rows)
    total = len(rows)
    train_n = max(1, int(total * 0.8)) if total else 0
    val_n = max(1, int(total * 0.1)) if total >= 3 else max(0, total - train_n)
    if train_n + val_n > total:
        val_n = max(0, total - train_n)
    test_n = total - train_n - val_n
    train = rows[:train_n]
    val = rows[train_n:train_n+val_n]
    test = rows[train_n+val_n:]
    for split, split_rows in [('train', train), ('validation', val), ('test', test)]:
        for r in split_rows:
            r['split'] = split
            r.setdefault('format', 'qwen2.5_chat')
    out = Path(args.out_dir)
    write_jsonl(out/'train.jsonl', train)
    write_jsonl(out/'validation.jsonl', val)
    write_jsonl(out/'test.jsonl', test)
    print(f'BUILD_INCREMENTAL_DATASET_OK=1 total={total} train={len(train)} validation={len(val)} test={len(test)}')

if __name__ == '__main__':
    main()
