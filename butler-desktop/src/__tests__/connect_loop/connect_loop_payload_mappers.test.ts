import { describe, expect, it } from 'vitest';
import { buildTargetBoxPayload } from '../../lib/connect_loop/client';
import { resolveCallableEndpoint, type RouterDecisionV1 } from '../../lib/connect_loop/contracts';

// maindev v1.2 이식 — 코덱스 구현 기준 조정:
//  buildBoxCallPlan({kind,payload}) → buildTargetBoxPayload(payload | null) (null = fallback).
//  정책 게이트는 매퍼가 아니라 resolveCallableEndpoint 책임(코덱스 분리) → non-allow 는 거기서 검증.
function decision(overrides: Partial<RouterDecisionV1> = {}): RouterDecisionV1 {
  return {
    request_id: 'req-1',
    intent_label: 'memory_search',
    target_box_id: 'helper1',
    target_endpoint: 'POST /v1/helpers/1/search',
    routing_confidence: 0.91,
    reason_code: 'INTENT_KEYWORD_MATCH',
    fallback_required: false,
    policy_precheck: 'allow',
    schema_version: 'router_decision.v1',
    ...overrides,
  };
}

describe('sidecar payload mapper (codex buildTargetBoxPayload)', () => {
  it('maps helper1 memory_search to measured Helper1Query schema', () => {
    const payload = buildTargetBoxPayload(decision(), '자료 찾아줘', { topK: 7 });
    expect(payload).toEqual({ query: '자료 찾아줘', top_k: 7 });
  });

  it('returns null (fallback) for box2 when our format is missing', () => {
    const payload = buildTargetBoxPayload(
      decision({ intent_label: 'form_convert', target_box_id: '2', target_endpoint: 'POST /v1/cards/2/rewrite' }),
      '외부 문서',
    );
    expect(payload).toBeNull();
  });

  it('maps box3 draft_write to measured Box3DraftRequest schema', () => {
    const payload = buildTargetBoxPayload(
      decision({ intent_label: 'draft_write', target_box_id: '3', target_endpoint: 'POST /v1/cards/3/draft' }),
      '새 초안을 작성해줘',
      { promptTemplate: '안전 지침', maxNewTokens: 256 },
    );
    expect(payload).toEqual({ input_text: '새 초안을 작성해줘', prompt_template: '안전 지침', max_new_tokens: 256 });
  });

  it('does not resolve a callable endpoint for non-allow decisions', () => {
    const d = decision({ policy_precheck: 'block', target_endpoint: 'none', fallback_required: true });
    expect(resolveCallableEndpoint(d)).toBeNull();
  });
});
