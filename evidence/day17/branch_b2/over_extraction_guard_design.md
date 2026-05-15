# Over-extraction Guard Design (Branch B-2, 자문 M-1~M-22 정합)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 720
- branch: B-2
- patch_type: over_extraction_guard
- verdict: MEASURED_ONLY

## 목적
PR #720 (Branch B-1) AB simulation 결과 action_fp Δ=+37 (over_extraction
증가) 검증. Branch B-2 는 **분해 강화 prompt 폐기**, **over_guard 우선**.

## Guard 적용 순서 (자문 2.2)
1. over_extraction_guard (1순위) — REPORT/QUESTION/NO_ACTION + non-action
   pattern 감지 시 action 생성 차단
2. evidence boundary 안정화 — evidence 누락 시 auto_apply hard block
3. 제한적 decomposition (5순위) — recoverable subset 만 분해 (cue 보유 +
   evidence 보유 + non-action 패턴 부재)

## Guard 패턴 (REPORT/QUESTION/NO_ACTION 한정)
- 가능한가요 / 확인 가능 / 알려주세요
- 어떻게 되 / 언제인가요 / 누구인가요 / 어디인가요
- 완료했습니다 / 보고드립니다 / 안내드립니다 / 공유했습니다 / 전달했습니다
- 하지 않아도 됩 / 취소되었 / 특별한 일정 없

## 결과 보고 영역
- A: current (Branch B-1 baseline) — guard 미적용
- B: over_guard_only — 1순위만 적용
- C: over_guard + limited_decomposition — 5순위 동반

## 선택 우선순위 (자문 2.5)
1. B 가 action_fp Δ ≤ 0 + safety 유지 → B 채택
2. C 가 action_fp Δ ≤ 0 + f1 Δ > B → C 채택
3. C 가 action_fp Δ > 0 → C 폐기 (B 채택)
