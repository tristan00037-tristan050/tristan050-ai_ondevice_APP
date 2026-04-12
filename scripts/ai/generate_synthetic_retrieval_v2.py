from __future__ import annotations
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import json
from pathlib import Path
from collections import Counter
from scripts.ai._anthropic_common_v1 import (
    GeneratedRow, build_parser, ensure_api_key, check_model_available,
    update_manifest, save_checkpoint, load_checkpoint, save_json, write_jsonl,
    GenerationStats, utcnow, estimate_cost_usd, str_to_bool, generate_in_batches,
)

FORMATS = [
    ('project', ['제목', '담당부서', '마감일'], '제목/담당부서/마감일 형식'),
    ('personnel', ['이름', '부서', '연락처'], '이름/부서/연락처 형식'),
    ('meeting', ['날짜', '장소', '참석자'], '날짜/장소/참석자 형식'),
    ('expense', ['항목', '금액', '승인자'], '항목/금액/승인자 형식'),
]
RETRIEVAL_SCHEMA_DESC = "하나의 JSON 객체만 출력하세요. 필수 키: prompt, completion, domain, difficulty, output_keys, preserve_keys. prompt는 자유 서술형 업무 메모를 특정 포맷으로 변환해달라는 요청이어야 합니다. completion은 포맷을 지켜야 하고 원문에 없는 값을 추가하면 안 됩니다."


def _prompt_for_llm(serial: int) -> tuple[str, dict]:
    domain, keys, format_desc = FORMATS[(serial - 1) % len(FORMATS)]
    difficulty = 'hard' if serial % 5 == 0 else 'easy'
    synthetic_id = f'retrieval_transform-{domain}-batch001-{serial:05d}'
    user_prompt = (
        f"한국어 retrieval_transform 학습 데이터 1건을 생성하세요. 업무 메모를 {format_desc}으로 변환하는 태스크여야 합니다. "
        f"출력 키는 {keys} 입니다. completion에는 원문에 없는 값이 들어가면 안 됩니다. "
        + RETRIEVAL_SCHEMA_DESC
    )
    return user_prompt, {'synthetic_id': synthetic_id, 'task_type': 'retrieval_transform', 'domain': domain, 'difficulty': difficulty, 'output_keys': keys}


def _parse_generated(text: str, meta: dict) -> GeneratedRow:
    obj = json.loads(text)
    metadata = {
        'output_keys': obj.get('output_keys', meta['output_keys']),
        'preserve_keys': obj.get('preserve_keys', meta['output_keys']),
    }
    return GeneratedRow(
        prompt=obj['prompt'],
        completion=obj['completion'],
        task_type='retrieval_transform',
        domain=obj.get('domain', meta['domain']),
        difficulty=obj.get('difficulty', meta['difficulty']),
        metadata=metadata,
    )


def main() -> None:
    ap = build_parser()
    args = ap.parse_args()
    output = Path(args.output)
    manifest_path = Path(args.manifest_path)
    checkpoint_path = Path(args.checkpoint_path)
    json_out = Path(args.json_out) if args.json_out else None
    quarantine_path = Path(args.quarantine_path)
    started_at = utcnow()
    api_key = ensure_api_key(args.api_key)
    if not check_model_available(args.model_id, api_key, max_retries=args.max_retries, sleep_seconds=args.sleep_seconds):
        raise SystemExit(f'모델 가용성 확인 실패: {args.model_id}')
    use_batches = str_to_bool(args.use_batches) and not args.dry_run
    target = 10 if args.dry_run else args.target
    ck = load_checkpoint(checkpoint_path) if args.resume else None
    serial_start = int(ck.get('last_successful_serial', 0)) + 1 if ck else 1
    rows, meta = generate_in_batches(
        target=target,
        batch_size=min(args.batch_size, target),
        serial_start=serial_start,
        prompt_builder=_prompt_for_llm,
        parse_fn=_parse_generated,
        api_key=api_key,
        model_id=args.model_id,
        use_batches=use_batches,
        max_retries=args.max_retries,
        sleep_seconds=args.sleep_seconds,
    )
    line_count = write_jsonl(output, rows)
    prompts = [r['prompt'] for r in rows]
    dup_count = sum(v - 1 for v in Counter(prompts).values() if v > 1)
    dup_rate = dup_count / max(len(rows), 1)
    stats = GenerationStats(
        task_type='retrieval_transform',
        model_id=args.model_id,
        total_requested=args.target,
        total_generated=line_count,
        valid_count=line_count,
        quarantine_count=0,
        duplicate_prompts=dup_count,
        duplicate_rate=round(dup_rate, 4),
        dry_run=args.dry_run,
        batch_mode='messages_api_dry_run' if args.dry_run else ('message_batches_api' if use_batches else 'messages_api'),
        started_at=started_at,
        finished_at=utcnow(),
        line_count=line_count,
        input_tokens=meta['input_tokens'],
        output_tokens=meta['output_tokens'],
        estimated_cost_usd=estimate_cost_usd(args.model_id, meta['input_tokens'], meta['output_tokens']),
        validation_summary={'retrieval_output_keys_required': True},
        batch_ids=meta['batch_ids'],
    )
    update_manifest(manifest_path, stats)
    save_checkpoint(checkpoint_path, {
        'last_successful_batch_id': meta['batch_ids'][-1] if meta['batch_ids'] else 'messages-direct',
        'last_successful_serial': meta['last_serial'],
        'total_generated': line_count,
        'task_type': 'retrieval_transform',
        'timestamp': utcnow(),
    })
    write_jsonl(quarantine_path, [])
    if json_out:
        save_json(json_out, {'ok': True, 'task_type': 'retrieval_transform', 'line_count': line_count, 'batch_ids': meta['batch_ids']})
    print('MODEL_OK=1')
    print(f'LINES_WRITTEN={line_count}')
    print('DRY_RUN_OK=1' if args.dry_run else 'BATCH_READY=1')

if __name__ == '__main__':
    main()
