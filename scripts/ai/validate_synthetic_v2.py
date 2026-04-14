from __future__ import annotations
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from scripts.ai._anthropic_common_v1 import read_jsonl, write_jsonl, save_json

POLITE = ('죄송', '안내', '드립니다', '감사')


def contains_json_hint(prompt: str) -> bool:
    return '{"tool_name"' in prompt or '반드시 다음 JSON 형식으로만 응답하세요' in prompt


def korean_char_count(text: str) -> int:
    return sum(1 for c in text if '가' <= c <= '힣')


def detect_hallucination(prompt: str, completion: str) -> bool:
    if '원문:' in prompt:
        source = prompt.split('원문:', 1)[1]
        nums = re.findall(r'[0-9]+(?:월|일|만원|명)?', completion)
        for n in nums:
            if n not in source:
                return True
    return False


def validate_rows(all_rows: list[dict]) -> tuple[dict, list[dict]]:
    total = len(all_rows)
    seen = Counter(r['prompt'] for r in all_rows)
    duplicate_items = sum(v - 1 for v in seen.values() if v > 1)
    dup_rate = duplicate_items / total if total else 0.0
    domain_counts = Counter(r.get('domain', 'unknown') for r in all_rows)
    reason_counts = Counter()
    quarantine = []
    hint_violations = 0

    for row in all_rows:
        t = row.get('task_type')
        prompt = row.get('prompt', '')
        completion = row.get('completion', '')
        fail = None
        if row.get('split') not in {'train', 'validation'}:
            fail = 'INVALID_SPLIT'
        elif row.get('source') != 'synthetic_claude_api':
            fail = 'SOURCE_MISMATCH'
        elif len(completion.strip()) < 20:
            fail = 'COMPLETION_TOO_SHORT'
        elif korean_char_count(completion) < 10:
            fail = 'NOT_ENOUGH_KOREAN'
        elif t == 'tool_call':
            if contains_json_hint(prompt):
                hint_violations += 1
                fail = 'TOOL_JSON_HINT'
            else:
                try:
                    obj = json.loads(completion)
                    if 'tool_name' not in obj:
                        fail = 'TOOL_NAME_MISSING'
                    elif not isinstance(obj.get('arguments'), dict) or not obj.get('arguments'):
                        fail = 'TOOL_ARGUMENTS_INVALID'
                except Exception:
                    fail = 'TOOL_JSON_INVALID'
        elif t == 'rewrite':
            original = prompt.split('다시 써주세요:', 1)[-1].strip()
            preserve = (row.get('quality_flags') or [{}])[0].get('preserve_keywords', [])
            preserve_ratio = 1.0 if not preserve else (sum(1 for k in preserve if k in completion) / len(preserve))
            if not any(w in completion for w in POLITE):
                fail = 'REWRITE_POLITE_MISSING'
            elif original == completion.strip():
                fail = 'REWRITE_VERBATIM'
            elif preserve_ratio < 0.7:
                fail = 'REWRITE_PRESERVE_LOW'
        elif t == 'retrieval_transform':
            qf = (row.get('quality_flags') or [{}])[0]
            keys = qf.get('output_keys', [])
            if not all(f'{k}:' in completion for k in keys):
                fail = 'RETRIEVAL_KEYS_MISSING'
            elif detect_hallucination(prompt, completion):
                fail = 'RETRIEVAL_HALLUCINATION'
        if fail:
            row = dict(row)
            row['reason_code'] = fail
            quarantine.append(row)
            reason_counts[fail] += 1

    valid_count = total - len(quarantine)
    pass_rate = (valid_count / total) if total else 0.0
    max_domain_share = max((v / total for v in domain_counts.values()), default=0.0)
    domain_imbalanced = max_domain_share > 0.40
    all_pass = pass_rate >= 0.95 and dup_rate < 0.01 and hint_violations == 0 and not domain_imbalanced
    result = {
        'total': total,
        'valid_count': valid_count,
        'quarantine_count': len(quarantine),
        'pass_rate': round(pass_rate, 4),
        'duplicate_count': duplicate_items,
        'duplicate_prompt_rate': round(dup_rate, 4),
        'tool_json_hint_violations': hint_violations,
        'reason_counts': dict(reason_counts),
        'domain_counts': dict(domain_counts),
        'domain_imbalanced': domain_imbalanced,
        'max_domain_share': round(max_domain_share, 4),
        'all_pass': all_pass,
    }
    return result, quarantine


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--inputs', nargs='+', required=True)
    ap.add_argument('--json-out', required=True)
    ap.add_argument('--quarantine-path', required=True)
    args = ap.parse_args()
    all_rows = []
    for p in args.inputs:
        all_rows.extend(read_jsonl(Path(p)))
    result, quarantine = validate_rows(all_rows)
    save_json(Path(args.json_out), result)
    write_jsonl(Path(args.quarantine_path), quarantine)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
