from __future__ import annotations
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import json
import random
from pathlib import Path
from collections import Counter
from scripts.ai._anthropic_common_v1 import (
    GeneratedRow, build_parser, ensure_api_key, check_model_available,
    update_manifest, save_checkpoint, load_checkpoint, save_json, write_jsonl,
    GenerationStats, utcnow, estimate_cost_usd, str_to_bool, generate_in_batches,
)

SCENARIOS = [
    ('배송', '배송이 지연되어 3일 후 도착합니다.'),
    ('결제', '결제 오류로 주문이 접수되지 않았습니다.'),
    ('서비스', '서비스가 다음 달부터 종료됩니다.'),
    ('가격', '가격이 다음 주부터 인상됩니다.'),
    ('약관', '약관이 일부 변경되었습니다.'),
    ('점검', '시스템 점검으로 일시 중단됩니다.'),
    ('반품', '반품 신청이 접수되었습니다.'),
    ('계정', '계정이 일시 정지되었습니다.'),
    ('혜택', '혜택 사용 기간이 만료되었습니다.'),
    ('주문', '주문이 고객 요청으로 취소되었습니다.'),
    ('예약', '예약 시간이 변경되었습니다.'),
    ('보안', '보안 점검으로 로그인 제한이 있습니다.'),
    ('법률', '본 약관 제15조에 따라 계약 해지 시 위약금이 부과될 수 있습니다.'),
    ('기술', 'TLS 인증서 교체 작업으로 API 호출이 지연될 수 있습니다.'),
]
REWRITE_SCHEMA_DESC = "하나의 JSON 객체만 출력하세요. 필수 키: prompt, completion, domain, difficulty, preserve_keywords. prompt에는 원문 문장이 들어가야 하고 completion은 공손한 한국어 재작성문입니다. preserve_keywords는 실제 completion에 유지되어야 할 핵심 단어 목록입니다."


def _prompt_for_llm(serial: int) -> tuple[str, dict]:
    topic, raw = SCENARIOS[(serial - 1) % len(SCENARIOS)]
    difficulty = 'hard' if topic in {'법률', '기술'} else 'easy'
    synthetic_id = f'rewrite-{topic}-batch001-{serial:05d}'
    user_prompt = (
        f"다음 주제({topic})의 한국어 rewrite 학습 데이터 1건을 생성하세요. 원문은 '{raw}' 를 기반으로 조금 변형해도 되지만 의미는 유지하세요. "
        "prompt는 '다음 문장을 고객 친화적이고 공손한 톤으로 다시 써주세요:'로 시작해야 합니다. completion은 공손 표현이 1개 이상 들어간 한국어 재작성문이어야 하며 원문과 완전히 같으면 안 됩니다. "
        + REWRITE_SCHEMA_DESC
    )
    return user_prompt, {'synthetic_id': synthetic_id, 'task_type': 'rewrite', 'domain': topic, 'difficulty': difficulty}


def _parse_generated(text: str, meta: dict) -> GeneratedRow:
    obj = json.loads(text)
    metadata = {'preserve_keywords': obj.get('preserve_keywords', [])}
    return GeneratedRow(
        prompt=obj['prompt'],
        completion=obj['completion'],
        task_type='rewrite',
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
        task_type='rewrite',
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
        validation_summary={'rewrite_polite_required': True},
        batch_ids=meta['batch_ids'],
    )
    update_manifest(manifest_path, stats)
    save_checkpoint(checkpoint_path, {
        'last_successful_batch_id': meta['batch_ids'][-1] if meta['batch_ids'] else 'messages-direct',
        'last_successful_serial': meta['last_serial'],
        'total_generated': line_count,
        'task_type': 'rewrite',
        'timestamp': utcnow(),
    })
    write_jsonl(quarantine_path, [])
    if json_out:
        save_json(json_out, {'ok': True, 'task_type': 'rewrite', 'line_count': line_count, 'batch_ids': meta['batch_ids']})
    print('MODEL_OK=1')
    print(f'LINES_WRITTEN={line_count}')
    print('DRY_RUN_OK=1' if args.dry_run else 'BATCH_READY=1')

if __name__ == '__main__':
    main()
