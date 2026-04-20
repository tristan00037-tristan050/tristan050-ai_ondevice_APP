from __future__ import annotations

from .runtime_contracts import PolicyConfig, TaskDecision, TaskType


def classify_task(text_meta: str, policy: PolicyConfig) -> TaskDecision:
    t = (text_meta or '').lower()
    if any(k in t for k in ['주민등록번호', '비밀번호', '계좌번호', '카드번호', '기밀']):
        return TaskDecision(TaskType.POLICY_SENSITIVE.value, 'sensitive_request')
    if any(k in t for k in ['마크다운 표', '표 형식', '계약 종료일', 'csv 데이터를', 'json 데이터를 마크다운']):
        if not policy.allow_retrieval_transform:
            return TaskDecision(TaskType.DIALOGUE.value, 'retrieval_policy_block', True)
        return TaskDecision(TaskType.RETRIEVAL_TRANSFORM.value, 'retrieval_transform_detected')
    if any(k in t for k in ['도구를 사용', 'tool schema', '데이터베이스', 'db query', '파일 경로', 'json strict', 'json 형식']):
        if not policy.allow_tool_call:
            return TaskDecision(TaskType.DIALOGUE.value, 'tool_call_policy_block', True)
        return TaskDecision(TaskType.TOOL_CALL.value, 'tool_call_detected')
    if any(k in t for k in ['요약', '정리']):
        return TaskDecision(TaskType.SUMMARIZE.value, 'summarize_detected')
    if any(k in t for k in ['다시 써', '공손한 톤', 'rewrite', '바꿔']):
        return TaskDecision(TaskType.REWRITE.value, 'rewrite_detected')
    return TaskDecision(TaskType.DIALOGUE.value, 'dialogue_fallback', True)
