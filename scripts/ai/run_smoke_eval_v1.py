from __future__ import annotations

import time
from typing import Any

from .phase_c_shared import score_smoke_case


def _fake_output(case: dict[str, Any], run_idx: int) -> str:
    func = case['function']
    if func == 'dialogue':
        return '안녕하세요. 이번 회의 일정과 업무 정리 내용을 검토해 보고드립니다. 다음 단계와 일정도 함께 확인 부탁드립니다.'
    if func == 'summarize':
        return '핵심 결론은 일정 조정과 비용 절감입니다. 주요 액션은 금요일까지 검토안을 제출하는 것입니다.'
    if func == 'rewrite':
        return '안내드립니다. 해당 내용은 확인 후 다시 말씀드리겠습니다. 불편을 드려 죄송합니다.'
    if func == 'tool_call':
        return '{"name":"get_weather","arguments":{"location":"서울"}}'
    if func == 'policy_sensitive':
        return '죄송하지만 해당 요청은 제공할 수 없습니다. 보안과 정책상 안내드릴 수 없습니다.'
    if func == 'retrieval_transform':
        return '이름: 홍길동\n부서: 운영팀\n연락처: 010-1111-2222'
    return '지원되지 않는 기능입니다.'


def _real_output(model, tokenizer, case: dict[str, Any], seed: int = 42) -> str:
    """실제 모델 추론 — real-run 전용."""
    import torch

    messages = [{'role': 'user', 'content': case['prompt']}]
    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors='pt',
        enable_thinking=False,
    ).to(model.device)
    with torch.no_grad():
        out = model.generate(
            inputs,
            max_new_tokens=256,
            temperature=0.0,
            do_sample=False,
        )
    return tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True).strip()


def run_smoke(rows: list[dict[str, Any]], latency_budget_ms: int, dry_run: bool = False,
              model=None, tokenizer=None) -> tuple[list[dict[str, Any]], bool]:
    smoke_results: list[dict[str, Any]] = []
    all_pass = True
    for run_idx in range(3):
        for row in rows:
            start = time.time()
            if dry_run:
                output = _fake_output(row, run_idx)
            else:
                output = _real_output(model, tokenizer, row, seed=42)
            latency_ms = int((time.time() - start) * 1000)
            if dry_run:
                latency_ms = max(1, latency_ms)
            res = score_smoke_case(row, output, latency_ms, latency_budget_ms)
            item = {
                'run_idx': run_idx + 1,
                'id': row['id'],
                'function': row['function'],
                'passed': res.passed,
                'latency_ms': res.latency_ms,
                'details': res.details,
            }
            smoke_results.append(item)
            if not res.passed:
                all_pass = False
    return smoke_results, all_pass
