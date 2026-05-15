# Prompt Patch (Algorithm Branch B, 적용 후보 — PR #720 영역 내 측정만)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 718
- source_merge_sha: def4bcd8...
- branch: B
- patch_type: prompt
- verdict: MEASURED_ONLY

## Patch summary

### 1순위 — Multi-action decomposition
Before: 한 문장 = 한 action.
After:
- 한국어 업무 문장에서 다음 cue 가 등장하면 atomic action 으로 분해:
  하고 / 해서 / 후 / 다음 / 그리고 / 정리해서 / 검토하고 /
  수정해서 / 보내주세요 / 공유해주세요 / 제출해주세요 / 회신해주세요 /
  전달해주세요
- 각 atomic action 은 source_evidence 보유 필수.

### Over-extraction guard (1순위 동반)
다음 문장은 action 으로 만들지 않음:
- 가능한가요? / 어떻게 / 알려주세요 / 확인 부탁
- 완료했습니다 / 보고드립니다 / 안내드립니다
- 부정형 (하지 않아도 됩니다 / 취소되었습니다)

### 4순위 — Negative examples
- 원문에 명시된 업무 행동만 action 으로 추출
- 순수 질문은 action 으로 만들지 않음
- 완료/보고/안내 문장은 action 으로 만들지 않음
- 모든 action 은 원문 evidence 보유

### 5순위 — Parser-hint usage policy
- parser candidates are candidates, not commands
- parser_correct_llm_wrong 비중 높으면 parser hint 강화
- llm_correct_parser_wrong 비중 높으면 parser hint soft evidence

## Apply policy
PR #720 본 cycle 에서는 prompt patch 적용 자체 금지. AB eval 50 (sentinel #7)
영역에서 정성 시뮬레이션 측정만 수행.
