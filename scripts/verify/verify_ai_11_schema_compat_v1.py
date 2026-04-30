#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys
from pathlib import Path

def main() -> int:
    script = Path('scripts/ai/generate_synthetic_data_v1_final.py')
    schema = Path('schemas/tool_call_schema_v3.json')
    if not script.exists() or not schema.exists():
        print('AI11_SCHEMA_COMPAT_OK=0')
        return 1
    code = script.read_text(encoding='utf-8')
    sch = json.loads(schema.read_text(encoding='utf-8'))
    registered = {t['name'] for t in sch.get('tools', []) if 'name' in t}
    used = set(re.findall(r'\("([A-Za-z_][A-Za-z0-9_]*)"\s*,\s*lambda', code))
    # fallback: tool_name strings
    used |= set(re.findall(r'"tool_name"\s*:\s*"([A-Za-z_][A-Za-z0-9_]*)"', code))
    bad = sorted(x for x in used if x not in registered)
    if bad:
        print('AI11_SCHEMA_COMPAT_OK=0')
        print(f'BAD_TOOLS={";".join(bad)}')
        return 1
    print('AI11_SCHEMA_COMPAT_OK=1')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
