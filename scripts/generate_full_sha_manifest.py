#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'FULL_SHA256_MANIFEST.txt'
EXCLUDE = {'FULL_SHA256_MANIFEST.txt'}
rows = []
for path in sorted(p for p in ROOT.rglob('*') if p.is_file()):
    rel = path.relative_to(ROOT).as_posix()
    if rel in EXCLUDE or rel.endswith('.zip') or '/__pycache__/' in rel or rel.endswith('.pyc'):
        continue
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    rows.append(f'{h}  {rel}')
OUT.write_text('\n'.join(rows) + '\n', encoding='utf-8')
print(f'MANIFEST_WRITTEN={OUT}')
print('SELF_HASH_EXCLUDED=true')
