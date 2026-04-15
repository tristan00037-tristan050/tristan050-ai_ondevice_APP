from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_eval_dataset(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open('r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def validate_eval_dataset(rows: list[dict[str, Any]]) -> tuple[bool, bool, float, list[dict[str, Any]]]:
    fail_cases = []
    required = {'id', 'function', 'prompt'}
    schema_total = len(rows)
    schema_pass = 0
    tool_ok = True
    for row in rows:
        if required.issubset(row.keys()):
            schema_pass += 1
        else:
            fail_cases.append({'id': row.get('id', ''), 'function': row.get('function', ''), 'reason': 'missing_fields'})
        if row.get('function') == 'tool_call':
            sch = row.get('tool_schema', {})
            if not (isinstance(sch, dict) and 'name' in sch and 'parameters' in sch):
                tool_ok = False
                fail_cases.append({'id': row.get('id', ''), 'function': 'tool_call', 'reason': 'schema_invalid'})
    schema_pass_rate = schema_pass / max(schema_total, 1)
    return schema_total == 12, tool_ok, schema_pass_rate, fail_cases
