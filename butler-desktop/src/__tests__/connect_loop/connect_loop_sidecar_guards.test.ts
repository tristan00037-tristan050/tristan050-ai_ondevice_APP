import { describe, expect, it, vi } from 'vitest';
import { assertValidRouterDecision, resolveCallableEndpoint, type RouterDecisionV1 } from '../../lib/connect_loop/contracts';
import { runChatBridge } from '../../lib/connect_loop/client';

async function stableHash(value: string): Promise<`sha256:${string}`> {
  const seed = Array.from(value).reduce((sum, c) => sum + c.charCodeAt(0), 0);
  return `sha256:${seed.toString(16).padStart(64, '0')}`;
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

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

  // Codex P2: Box3 실제 응답은 draft_text 키 → displayText 로 노출되어야 함.
  it('surfaces Box3 draft_text in displayText', async () => {
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      if (url.endsWith('/v1/router/decide')) {
        return jsonResponse({
          decision: {
            request_id: body.chat_request.request_id,
            intent_label: 'draft_write',
            target_box_id: '3',
            target_endpoint: 'POST /v1/cards/3/draft',
            routing_confidence: 0.9,
            reason_code: 'INTENT_KEYWORD_MATCH',
            fallback_required: false,
            policy_precheck: 'allow',
            schema_version: 'router_decision.v1',
          },
        });
      }
      return jsonResponse({ draft_text: '생성된 초안 본문', external_send_zero: true, raw_doc_logged: false });
    });
    const result = await runChatBridge('새 상황 보고서 초안 작성', {
      hashText: stableHash,
      fetcher,
      capabilityTokenProvider: async () => 'test-token',
    });
    expect(result.status).toBe('executed');
    expect(result.displayText).toBe('생성된 초안 본문');
  });
});
