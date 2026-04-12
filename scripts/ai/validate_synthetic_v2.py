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
from scripts.ai._anthropic_common_v1 import read_jsonl, write_jsonl, save_json

POLITE = ('죄송', '안내', '드립니다', '감사')
MIN_LENGTH_BY_TASK = {
    'tool_call': 10,
    'retrieval_transform': 10,
    'rewrite': 20,
    'dialogue': 20,
}
KOREAN_CHECK_EXEMPT = {'tool_call'}


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


def _common_fail(row: dict, duplicate_prompts: set[str]) -> str | None:
    prompt = row.get('prompt', '')
    completion = row.get('completion', '')
    if not prompt.strip() or not completion.strip():
        return 'MISSING_PROMPT_OR_COMPLETION'
    if prompt in duplicate_prompts:
        return 'DUPLICATE_PROMPT'
    if row.get('split') not in {'train', 'validation'}:
        return 'INVALID_SPLIT'
    if row.get('source') != 'synthetic_claude_api':
        return 'SOURCE_MISMATCH'
    return None


def _validate_tool_call(row: dict, completion: str) -> str | None:
    prompt = row.get('prompt', '')
    if len(completion.strip()) < MIN_LENGTH_BY_TASK['tool_call']:
        return 'COMPLETION_TOO_SHORT'
    if contains_json_hint(prompt):
        return 'TOOL_JSON_HINT'
    try:
        obj = json.loads(completion)
    except Exception:
        return 'TOOL_JSON_INVALID'
    if 'tool_name' not in obj:
        return 'TOOL_NAME_MISSING'
    args_obj = obj.get('arguments')
    if not isinstance(args_obj, dict) or not args_obj:
        return 'TOOL_ARGUMENTS_INVALID'
    return None


def _validate_rewrite(row: dict, completion: str) -> str | None:
    if len(completion.strip()) < MIN_LENGTH_BY_TASK['rewrite']:
        return 'COMPLETION_TOO_SHORT'
    if korean_char_count(completion) < 10:
        return 'NOT_ENOUGH_KOREAN'
    original = row.get('prompt', '').split('다시 써주세요:', 1)[-1].strip()
    preserve = (row.get('quality_flags') or [{}])[0].get('preserve_keywords', [])
    preserve_ratio = 1.0 if not preserve else (sum(1 for k in preserve if k in completion) / len(preserve))
    if not any(w in completion for w in POLITE):
        return 'REWRITE_POLITE_MISSING'
    if original == completion.strip():
        return 'REWRITE_VERBATIM'
    if preserve_ratio < 0.7:
        return 'REWRITE_PRESERVE_LOW'
    return None


def _validate_retrieval(row: dict, completion: str) -> str | None:
    qf = (row.get('quality_flags') or [{}])[0]
    keys = qf.get('output_keys', [])
    preserve = qf.get('preserve_keys', [])
    if not all(f'{k}:' in completion for k in keys):
        return 'RETRIEVAL_KEYS_MISSING'
    if preserve and not all(k in completion for k in preserve):
        return 'RETRIEVAL_KEYS_MISSING'
    if detect_hallucination(row.get('prompt', ''), completion):
        return 'RETRIEVAL_HALLUCINATION'
    if len(completion.strip()) < MIN_LENGTH_BY_TASK['retrieval_transform']:
        return 'COMPLETION_TOO_SHORT'
    if korean_char_count(completion) < 10:
        return 'NOT_ENOUGH_KOREAN'
    return None


def _validate_generic(row: dict, completion: str) -> str | None:
    task_type = row.get('task_type') or row.get('function') or ''
    min_len = MIN_LENGTH_BY_TASK.get(task_type, 20)
    if len(completion.strip()) < min_len:
        return 'COMPLETION_TOO_SHORT'
    if task_type not in KOREAN_CHECK_EXEMPT and korean_char_count(completion) < 10:
        return 'NOT_ENOUGH_KOREAN'
    return None


def validate_rows(all_rows: list[dict]) -> tuple[dict, list[dict]]:
    total = len(all_rows)
    prompt_counts = Counter(r.get('prompt', '') for r in all_rows)
    duplicate_prompts = {p for p, c in prompt_counts.items() if p and c > 1}
    domain_counts = Counter(r.get('domain', 'unknown') for r in all_rows)
    reason_counts = Counter()
    quarantine: list[dict] = []
    hint_violations = 0

    for row in all_rows:
        completion = row.get('completion', '')
        task_type = row.get('task_type') or row.get('function') or ''
        fail = _common_fail(row, duplicate_prompts)
        if fail is None:
            if task_type == 'tool_call':
                fail = _validate_tool_call(row, completion)
                if fail == 'TOOL_JSON_HINT':
                    hint_violations += 1
            elif task_type == 'retrieval_transform':
                fail = _validate_retrieval(row, completion)
            elif task_type == 'rewrite':
                fail = _validate_rewrite(row, completion)
            else:
                fail = _validate_generic(row, completion)
        if fail:
            bad = dict(row)
            bad['reason_code'] = fail
            quarantine.append(bad)
            reason_counts[fail] += 1

    quarantine_count = len(quarantine)
    valid_count = max(0, total - quarantine_count)
    pass_rate = (valid_count / total) if total else 0.0
    duplicate_quarantine_count = reason_counts.get('DUPLICATE_PROMPT', 0)
    dup_rate = (duplicate_quarantine_count / total) if total else 0.0
    max_domain_share = max((v / total for v in domain_counts.values()), default=0.0)
    domain_imbalanced = total >= 100 and max_domain_share > 0.40
    all_pass = pass_rate >= 0.95 and dup_rate < 0.01 and hint_violations == 0 and not domain_imbalanced
    result = {
        'total': total,
        'valid_count': valid_count,
        'quarantine_count': quarantine_count,
        'pass_rate': round(pass_rate, 4),
        'duplicate_count': duplicate_quarantine_count,
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
