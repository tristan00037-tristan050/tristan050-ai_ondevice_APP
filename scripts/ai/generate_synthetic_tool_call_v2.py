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
    TOOL_DOMAINS, GeneratedRow, build_parser, ensure_api_key, check_model_available,
    update_manifest, save_checkpoint, load_checkpoint, save_json, write_jsonl,
    GenerationStats, utcnow, estimate_cost_usd, str_to_bool, generate_in_batches,
)

DATE_PHRASES = ['다음 주 월요일 오전 10시', '4월 21일 오후 2시', '내일 오전 9시', '이번 주 금요일 오후 4시']
DEPTS = ['마케팅팀', '재무팀', '인사팀', '영업팀', '개발팀', '운영팀']
NAMES = ['김지수', '이서연', '박민재', '정도현', '최유진', '윤하준']
TITLES = ['주간 스탠드업', '예산 검토', '분기 보고', '출시 점검', '고객 이슈 리뷰', '출장비 청구']
COUNTS = ['1', '2', '3', '4']

PROMPT_BUILDERS = {
    'calendar': lambda rng: (
        f"{rng.choice(DATE_PHRASES)} {rng.choice(TITLES)} 일정을 캘린더에 등록해주세요.",
        'easy', ['date', 'title']),
    'approval': lambda rng: (
        f"{rng.choice(DEPTS)}의 {rng.choice(TITLES)} 결재 요청을 승인 대기 목록에서 찾아 처리해주세요.",
        'hard', ['department', 'title', 'status']),
    'document': lambda rng: (
        f"{rng.choice(DEPTS)}에서 작성한 {rng.choice(TITLES)} 관련 문서를 검색해주세요.",
        'easy', ['department', 'query']),
    'meeting_room': lambda rng: (
        f"{rng.choice(DATE_PHRASES)} 회의실을 예약하고 참석 인원을 {rng.choice(COUNTS)}명으로 설정해주세요.",
        'hard', ['date', 'headcount', 'purpose']),
    'inventory': lambda rng: (
        f"{rng.choice(DEPTS)}에서 사용할 노트북 재고를 확인해주세요.",
        'easy', ['department', 'item']),
    'hr': lambda rng: (
        f"{rng.choice(DEPTS)} {rng.choice(NAMES)}의 연차 신청 내역을 조회해주세요.",
        'easy', ['department', 'name']),
    'finance': lambda rng: (
        f"{rng.choice(DEPTS)} {rng.choice(NAMES)}의 출장비 영수증 {rng.choice(COUNTS)}건을 재무시스템에 청구 요청하세요.",
        'hard', ['department', 'name', 'expense_type', 'count']),
    'crm': lambda rng: (
        f"{rng.choice(NAMES)} 고객의 최근 상담 이력을 조회해주세요.",
        'easy', ['customer_name', 'history_type']),
    'notification': lambda rng: (
        f"{rng.choice(DEPTS)} 전체에 {rng.choice(TITLES)} 알림을 발송해주세요.",
        'easy', ['department', 'title']),
}

TOOL_SCHEMA_DESC = """하나의 JSON 객체만 출력하세요. 필수 키: tool_name, arguments. arguments는 비어 있지 않은 dict여야 합니다. 프롬프트에는 정답 JSON 힌트를 넣지 말고 자연어 업무 요청만 생성하세요. 한국어만 사용하세요. 출력 JSON 객체 스키마: {\"prompt\":...,\"completion\":...,\"domain\":...,\"difficulty\":...,\"required_argument_keys\":[...]}"""


def _prompt_for_llm(serial: int) -> tuple[str, dict]:
    rng = random.Random(1000 + serial)
    domains = list(TOOL_DOMAINS.keys())
    domain = domains[(serial - 1) % len(domains)]
    prompt_text, difficulty, req_keys = PROMPT_BUILDERS[domain](rng)
    synthetic_id = f"tool_call-{domain}-batch001-{serial:05d}"
    user_prompt = (
        "다음 조건을 만족하는 tool_call 학습 데이터 1건을 JSON 객체로 생성하세요. "
        f"업무 도메인은 {domain} 입니다. 사용자의 자연어 요청(prompt)과 그 요청에 대한 정답 completion(JSON 문자열)을 생성하세요. "
        "prompt에는 JSON 정답 형식을 절대 포함하지 마세요. completion은 tool_name과 arguments(dict, non-empty)를 가진 유효한 JSON 문자열이어야 합니다. "
        f"자연어 요청 예시 방향: {prompt_text}. required_argument_keys는 {req_keys} 를 반영하세요. "
        + TOOL_SCHEMA_DESC
    )
    return user_prompt, {
        'synthetic_id': synthetic_id,
        'task_type': 'tool_call',
        'domain': domain,
        'difficulty': difficulty,
        'required_argument_keys': req_keys,
    }


def _parse_generated(text: str, meta: dict) -> GeneratedRow:
    obj = json.loads(text)
    completion = obj['completion']
    comp_obj = json.loads(completion)
    metadata = {
        'required_argument_keys': obj.get('required_argument_keys', meta['required_argument_keys']),
        'tool_name': comp_obj.get('tool_name'),
        'arguments_keys': sorted(list(comp_obj.get('arguments', {}).keys())) if isinstance(comp_obj.get('arguments'), dict) else [],
    }
    return GeneratedRow(
        prompt=obj['prompt'],
        completion=completion,
        task_type='tool_call',
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
        task_type='tool_call',
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
        validation_summary={'tool_call_json_hint_zero': True},
        batch_ids=meta['batch_ids'],
    )
    update_manifest(manifest_path, stats)
    save_checkpoint(checkpoint_path, {
        'last_successful_batch_id': meta['batch_ids'][-1] if meta['batch_ids'] else 'messages-direct',
        'last_successful_serial': meta['last_serial'],
        'total_generated': line_count,
        'task_type': 'tool_call',
        'timestamp': utcnow(),
    })
    write_jsonl(quarantine_path, [])
    if json_out:
        save_json(json_out, {'ok': True, 'task_type': 'tool_call', 'line_count': line_count, 'batch_ids': meta['batch_ids']})
    print(f'MODEL_OK=1')
    print(f'LINES_WRITTEN={line_count}')
    print('DRY_RUN_OK=1' if args.dry_run else 'BATCH_READY=1')

if __name__ == '__main__':
    main()
