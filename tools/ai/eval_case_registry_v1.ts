'use strict';

import type { EvalCaseV1 } from './eval_fingerprint_v2';

/**
 * eval case 데이터 진실원(SSOT)은 scripts/ai/prepare_eval_cases_v1.py.
 * 이 파일은 결과 소비용 타입 선언만 유지한다.
 * 동일 eval case 데이터를 TS에 중복 정의하지 않는다.
 */

export type { EvalCaseV1 };

export const EVAL_CASE_COUNT = 24 as const;

export const EVAL_CASE_CLASS_COUNTS: Record<EvalCaseV1['prompt_class_id'], number> = {
  qa: 6,
  summarize: 4,
  rewrite: 4,
  tool_call: 4,
  policy_sensitive: 3,
  retrieval_transform: 3,
} as const;
