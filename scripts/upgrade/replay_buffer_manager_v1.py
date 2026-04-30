#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, random
from pathlib import Path
from collections import defaultdict


def load_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for r in rows:
        dig = r.get('prompt_digest_sha256')
        if not dig or dig in seen:
            continue
        seen.add(dig)
        out.append(r)
    return out


def cap_per_bucket(rows: list[dict], max_per_bucket: int) -> list[dict]:
    buckets = defaultdict(list)
    for r in rows:
        buckets[(r.get('function'), r.get('lang'))].append(r)
    out = []
    for items in buckets.values():
        random.shuffle(items)
        out.extend(items[:max_per_bucket])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description='Merge incremental data with replay buffer')
    ap.add_argument('--incoming', required=True)
    ap.add_argument('--replay', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-per-bucket', type=int, default=4000)
    args = ap.parse_args()
    random.seed(42)
    rows = load_jsonl(Path(args.replay)) + load_jsonl(Path(args.incoming))
    rows = dedupe(rows)
    rows = cap_per_bucket(rows, args.max_per_bucket)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'REPLAY_BUFFER_OK=1 rows={len(rows)}')


if __name__ == '__main__':
    main()
