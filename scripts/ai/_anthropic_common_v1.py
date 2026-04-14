from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

DEFAULT_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_VERSION = "2023-06-01"
MAX_BATCH_REQUESTS = 100_000
MAX_BATCH_BYTES = 256 * 1024 * 1024

SYSTEM_PROMPT = (
    "당신은 버틀러 AI 플랫폼의 한국어 합성 학습 데이터 생성기입니다. "
    "실제 제품 태스크와 일치하는 고품질 데이터만 생성하세요. "
    "정답 힌트, 플레이스홀더, 영어 위주 출력, JSON 스키마 위반, 과도한 boilerplate를 금지합니다."
)

POLITE_WORDS = ("안내", "드립니다", "감사", "죄송")
TOOL_DOMAINS = {
    "calendar": ["calendar_add", "calendar_search", "schedule_meeting"],
    "approval": ["approve_request", "reject_request", "submit_approval"],
    "document": ["document_search", "file_search", "report_query"],
    "meeting_room": ["room_reserve", "room_cancel", "room_check_availability"],
    "inventory": ["inventory_check", "stock_query", "supply_request"],
    "hr": ["employee_search", "leave_request", "overtime_record"],
    "finance": ["expense_claim", "budget_query", "payment_request"],
    "crm": ["customer_lookup", "complaint_register", "account_info"],
    "notification": ["send_notification", "send_email", "create_reminder"],
}

class ConfigError(RuntimeError):
    pass

@dataclass
class GenerationStats:
    task_type: str
    model_id: str
    total_requested: int
    total_generated: int
    valid_count: int
    quarantine_count: int
    duplicate_prompts: int
    duplicate_rate: float
    dry_run: bool
    batch_mode: str
    started_at: str
    finished_at: str
    line_count: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    validation_summary: dict[str, Any]
    batch_ids: list[str]

@dataclass
class GeneratedRow:
    prompt: str
    completion: str
    task_type: str
    domain: str
    difficulty: str
    metadata: dict[str, Any]

@dataclass
class HTTPResponse:
    status: int
    data: dict[str, Any]
    headers: dict[str, str]


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def sha16(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def deterministic_split(synthetic_id: str) -> str:
    h = int(hashlib.sha256(synthetic_id.encode('utf-8')).hexdigest(), 16) % 100
    return 'validation' if h < 5 else 'train'


def ensure_api_key(api_key: str | None = None) -> str:
    key = api_key or os.getenv('ANTHROPIC_API_KEY')
    if not key:
        raise ConfigError('ANTHROPIC_API_KEY가 없습니다. --api-key 또는 환경변수를 설정하세요.')
    return key


def batch_headers(api_key: str) -> dict[str, str]:
    return {
        'x-api-key': api_key,
        'anthropic-version': ANTHROPIC_VERSION,
        'content-type': 'application/json',
    }


def _http_request(url: str, method: str = 'GET', headers: dict[str, str] | None = None,
                  payload: dict[str, Any] | None = None, timeout: int = 120) -> HTTPResponse:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8')
            parsed = json.loads(body) if body else {}
            return HTTPResponse(status=resp.status, data=parsed, headers=dict(resp.headers))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {'raw_error': body}
        parsed['_http_status'] = e.code
        parsed['_headers'] = dict(e.headers)
        raise RuntimeError(json.dumps(parsed, ensure_ascii=False)) from e


def request_with_retries(url: str, *, method: str = 'GET', headers: dict[str, str] | None = None,
                         payload: dict[str, Any] | None = None, timeout: int = 120,
                         max_retries: int = 5, sleep_seconds: float = 1.0) -> HTTPResponse:
    attempt = 0
    while True:
        try:
            return _http_request(url, method=method, headers=headers, payload=payload, timeout=timeout)
        except RuntimeError as e:
            attempt += 1
            try:
                data = json.loads(str(e))
            except Exception:
                data = {'_http_status': 500}
            status = int(data.get('_http_status', 500))
            hdrs = data.get('_headers', {}) or {}
            if status == 429 and attempt <= max_retries:
                retry_after = float(hdrs.get('retry-after', sleep_seconds))
                time.sleep(retry_after)
                continue
            if status >= 500 and attempt <= max_retries:
                time.sleep(sleep_seconds * (2 ** (attempt - 1)))
                continue
            raise


def list_models(api_key: str, max_retries: int = 5, sleep_seconds: float = 1.0) -> list[dict[str, Any]]:
    resp = request_with_retries(
        'https://api.anthropic.com/v1/models',
        headers=batch_headers(api_key),
        max_retries=max_retries,
        sleep_seconds=sleep_seconds,
    )
    return list(resp.data.get('data', []))


def check_model_available(model_id: str, api_key: str, max_retries: int = 5,
                          sleep_seconds: float = 1.0) -> bool:
    models = {m.get('id') for m in list_models(api_key, max_retries=max_retries, sleep_seconds=sleep_seconds)}
    return model_id in models


def messages_create(params: dict[str, Any], api_key: str, max_retries: int = 5,
                    sleep_seconds: float = 1.0) -> dict[str, Any]:
    resp = request_with_retries(
        'https://api.anthropic.com/v1/messages',
        method='POST',
        headers=batch_headers(api_key),
        payload=params,
        max_retries=max_retries,
        sleep_seconds=sleep_seconds,
    )
    return resp.data


def create_message_batch(requests: list[dict[str, Any]], api_key: str,
                         max_retries: int = 5, sleep_seconds: float = 1.0) -> dict[str, Any]:
    payload = {'requests': requests}
    encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    if len(requests) > MAX_BATCH_REQUESTS:
        raise ConfigError(f'배치 요청 수 초과: {len(requests)} > {MAX_BATCH_REQUESTS}')
    if len(encoded) > MAX_BATCH_BYTES:
        raise ConfigError(f'배치 크기 초과: {len(encoded)} > {MAX_BATCH_BYTES}')
    resp = request_with_retries(
        'https://api.anthropic.com/v1/messages/batches',
        method='POST',
        headers=batch_headers(api_key),
        payload=payload,
        max_retries=max_retries,
        sleep_seconds=sleep_seconds,
    )
    return resp.data


def retrieve_batch(batch_id: str, api_key: str, max_retries: int = 5,
                   sleep_seconds: float = 1.0) -> dict[str, Any]:
    resp = request_with_retries(
        f'https://api.anthropic.com/v1/messages/batches/{batch_id}',
        headers=batch_headers(api_key),
        max_retries=max_retries,
        sleep_seconds=sleep_seconds,
    )
    return resp.data


def poll_batch_until_done(batch_id: str, api_key: str, sleep_seconds: float = 60.0,
                          max_polls: int = 1440, max_retries: int = 5) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for _ in range(max_polls):
        last = retrieve_batch(batch_id, api_key, max_retries=max_retries, sleep_seconds=sleep_seconds)
        if last.get('processing_status') == 'ended':
            return last
        time.sleep(sleep_seconds)
    raise RuntimeError(f'배치가 종료되지 않았습니다: {batch_id}')


def iter_batch_results(batch_id: str, api_key: str, max_retries: int = 5,
                       sleep_seconds: float = 1.0) -> Iterator[dict[str, Any]]:
    url = f'https://api.anthropic.com/v1/messages/batches/{batch_id}/results'
    headers = batch_headers(api_key)
    attempts = 0
    while True:
        req = urllib.request.Request(url, headers=headers, method='GET')
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw_line in resp.read().decode('utf-8').splitlines():
                    line = raw_line.strip()
                    if line:
                        yield json.loads(line)
                return
        except urllib.error.HTTPError as e:
            attempts += 1
            if e.code == 429 and attempts <= max_retries:
                retry_after = float(e.headers.get('retry-after', sleep_seconds))
                time.sleep(retry_after)
                continue
            raise


def text_from_message_response(data: dict[str, Any]) -> str:
    content = data.get('content', [])
    chunks = []
    for part in content:
        if part.get('type') == 'text':
            chunks.append(part.get('text', ''))
    return ''.join(chunks).strip()


def text_from_batch_result(result_line: dict[str, Any]) -> str:
    result = result_line.get('result', {})
    if result.get('type') != 'succeeded':
        return ''
    message = result.get('message', {})
    return text_from_message_response(message)


def make_generation_payload(model_id: str, user_prompt: str, max_tokens: int = 900) -> dict[str, Any]:
    return {
        'model': model_id,
        'max_tokens': max_tokens,
        'temperature': 0.3,
        'system': SYSTEM_PROMPT,
        'messages': [{'role': 'user', 'content': user_prompt}],
    }


def make_batch_request(custom_id: str, model_id: str, user_prompt: str, max_tokens: int = 900) -> dict[str, Any]:
    return {'custom_id': custom_id, 'params': make_generation_payload(model_id, user_prompt, max_tokens=max_tokens)}


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
            count += 1
    return count


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open('a', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
            count += 1
    return count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def save_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def count_tokens_estimate(text: str) -> int:
    return max(1, len(text) // 3)


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    if 'sonnet-4' in model_id:
        return round((input_tokens / 1_000_000) * 3.0 + (output_tokens / 1_000_000) * 15.0, 4)
    return round((input_tokens / 1_000_000) * 3.0 + (output_tokens / 1_000_000) * 15.0, 4)


def build_common_row(prompt: str, completion: str, task_type: str, synthetic_id: str,
                     domain: str, difficulty: str, model_id: str, batch_id: str) -> dict[str, Any]:
    return {
        'prompt': prompt,
        'completion': completion,
        'function': task_type,
        'task_type': task_type,
        'lang': 'ko',
        'format': 'qwen2.5_chat',
        'source': 'synthetic_claude_api',
        'split': deterministic_split(synthetic_id),
        'synthetic_id': synthetic_id,
        'domain': domain,
        'difficulty': difficulty,
        'generated_by_model': model_id,
        'generated_at': utcnow(),
        'generation_batch_id': batch_id,
        'quality_flags': [],
    }


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    save_json(path, payload)


def update_manifest(path: Path, stats: GenerationStats) -> None:
    save_json(path, asdict(stats))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', required=True, type=int)
    ap.add_argument('--batch-size', default=20, type=int)
    ap.add_argument('--output', required=True)
    ap.add_argument('--api-key', default=None)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--use-batches', default='true')
    ap.add_argument('--max-retries', default=5, type=int)
    ap.add_argument('--sleep-seconds', default=1.0, type=float)
    ap.add_argument('--manifest-path', default='data/synthetic/manifest.json')
    ap.add_argument('--quarantine-path', default='data/synthetic/quarantine.jsonl')
    ap.add_argument('--model-id', default=DEFAULT_MODEL)
    ap.add_argument('--checkpoint-path', default='data/synthetic/checkpoint.json')
    ap.add_argument('--json-out', default=None)
    return ap


def str_to_bool(v: str | bool) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def generate_in_batches(target: int, batch_size: int, serial_start: int,
                        prompt_builder: Callable[[int], tuple[str, dict[str, Any]]],
                        parse_fn: Callable[[str, dict[str, Any]], GeneratedRow],
                        *, api_key: str, model_id: str, use_batches: bool,
                        max_retries: int, sleep_seconds: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    batch_ids: list[str] = []
    total_input = 0
    total_output = 0
    generated = 0
    current_serial = serial_start

    if use_batches:
        while generated < target:
            remaining = target - generated
            this_n = min(batch_size, remaining)
            request_items = []
            mapping: dict[str, dict[str, Any]] = {}
            for _ in range(this_n):
                prompt, meta = prompt_builder(current_serial)
                custom_id = meta['synthetic_id']
                request_items.append(make_batch_request(custom_id, model_id, prompt))
                mapping[custom_id] = {'prompt': prompt, 'meta': meta}
                total_input += count_tokens_estimate(prompt)
                current_serial += 1
            created = create_message_batch(request_items, api_key, max_retries=max_retries, sleep_seconds=sleep_seconds)
            batch_id = created['id']
            batch_ids.append(batch_id)
            final = poll_batch_until_done(batch_id, api_key, sleep_seconds=max(5.0, sleep_seconds), max_retries=max_retries)
            for result_line in iter_batch_results(batch_id, api_key, max_retries=max_retries, sleep_seconds=sleep_seconds):
                cid = result_line.get('custom_id')
                ctx = mapping.get(cid)
                if not ctx:
                    continue
                txt = text_from_batch_result(result_line)
                if txt:
                    parsed = parse_fn(txt, ctx['meta'])
                    row = build_common_row(ctx['prompt'], parsed.completion, parsed.task_type, ctx['meta']['synthetic_id'], parsed.domain, parsed.difficulty, model_id, batch_id)
                    row['quality_flags'] = [parsed.metadata]
                    rows.append(row)
                    total_output += count_tokens_estimate(parsed.completion)
                else:
                    row = build_common_row(ctx['prompt'], '', ctx['meta']['task_type'], ctx['meta']['synthetic_id'], ctx['meta']['domain'], ctx['meta']['difficulty'], model_id, batch_id)
                    row['quality_flags'] = [{'batch_error': result_line.get('result', {}).get('type', 'unknown')}]
                    rows.append(row)
            generated += this_n
    else:
        while generated < target:
            prompt, meta = prompt_builder(current_serial)
            payload = make_generation_payload(model_id, prompt)
            resp = messages_create(payload, api_key, max_retries=max_retries, sleep_seconds=sleep_seconds)
            txt = text_from_message_response(resp)
            parsed = parse_fn(txt, meta)
            row = build_common_row(prompt, parsed.completion, parsed.task_type, meta['synthetic_id'], parsed.domain, parsed.difficulty, model_id, 'messages-direct')
            row['quality_flags'] = [parsed.metadata]
            rows.append(row)
            total_input += resp.get('usage', {}).get('input_tokens', count_tokens_estimate(prompt))
            total_output += resp.get('usage', {}).get('output_tokens', count_tokens_estimate(parsed.completion))
            current_serial += 1
            generated += 1
            time.sleep(sleep_seconds)
    return rows, {'batch_ids': batch_ids, 'input_tokens': total_input, 'output_tokens': total_output, 'last_serial': current_serial - 1}
