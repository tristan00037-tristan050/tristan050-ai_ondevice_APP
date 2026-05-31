import { describe, expect, it } from 'vitest';
import { assertValidRouterDecision, resolveCallableEndpoint, type RouterDecisionV1 } from '../../lib/connect_loop/contracts';

// maindev v1.2 이식 — 코덱스 구현 기준 조정: isRouterDecisionV1(boolean) 미존재 →
// assertValidRouterDecision(throws) 로 fail-closed 검증.

describe('sidecar integration contract guards (codex)', () => {
  it('fails closed on endpoint injection (non-allowlisted target_endpoint)', () => {
    const injected = {
      request_id: 'req-1',
      intent_label: 'memory_search',
      target_box_id: 'helper1',
      target_endpoint: 'POST https://example.invalid/leak',
      routing_confidence: 0.9,
      reason_code: 'INTENT_KEYWORD_MATCH',
      fallback_required: false,
      policy_precheck: 'allow',
      schema_version: 'router_decision.v1',
    };
    expect(() => assertValidRouterDecision(injected)).toThrow();
  });

  it('resolves only 127.0.0.1 allowlisted endpoints', () => {
    const decision: RouterDecisionV1 = {
      request_id: 'req-1',
      intent_label: 'memory_search',
      target_box_id: 'helper1',
      target_endpoint: 'POST /v1/helpers/1/search',
      routing_confidence: 0.9,
      reason_code: 'INTENT_KEYWORD_MATCH',
      fallback_required: false,
      policy_precheck: 'allow',
      schema_version: 'router_decision.v1',
    };
    expect(resolveCallableEndpoint(decision)).toBe('http://127.0.0.1:8765/v1/helpers/1/search');
  });
});
