import { describe, expect, it } from 'vitest';
import { buildTargetBoxPayload } from '../../lib/connect_loop/client';
import { resolveCallableEndpoint, type RouterDecisionV1 } from '../../lib/connect_loop/contracts';

const REQUEST_ID = '9699ce0c-2597-42ea-a6fa-29cfcb2bb75e';
const WORKSPACE_ID = '90321a6a-f937-4d93-b018-d09e8cab4e72';

function decision(overrides: Partial<RouterDecisionV1> = {}): RouterDecisionV1 {
  return {
    request_id: REQUEST_ID,
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
  it('maps helper1 memory_search to the strict Helper1 v2 envelope', () => {
    const payload = buildTargetBoxPayload(
      decision(),
      '자료 찾아줘',
      { topK: 7, helper1WorkspaceId: WORKSPACE_ID },
    );
    expect(payload).toEqual({
      schema_version: 'butler.helper1.ask-request.v2',
      request_id: REQUEST_ID,
      workspace_id: WORKSPACE_ID,
      query: '자료 찾아줘',
      top_k: 7,
      requested_generation_id: null,
      effect_intent: 'display_only',
    });
  });

  it('fails closed when memory_search has no approved workspace', () => {
    expect(buildTargetBoxPayload(decision(), '자료 찾아줘')).toBeNull();
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

  it('blocks memory_search query exceeding helper1 4000 cap', () => {
    const over = 'ㄱ'.repeat(4001);
    expect(buildTargetBoxPayload(
      decision(),
      over,
      { helper1WorkspaceId: WORKSPACE_ID },
    )).toBeNull();
    const ok = 'ㄱ'.repeat(4000);
    expect(buildTargetBoxPayload(
      decision(),
      ok,
      { helper1WorkspaceId: WORKSPACE_ID },
    )).toMatchObject({ query: ok, top_k: 5 });
  });

  it('does not resolve a callable endpoint for non-allow decisions', () => {
    const d = decision({ policy_precheck: 'block', target_endpoint: 'none', fallback_required: true });
    expect(resolveCallableEndpoint(d)).toBeNull();
  });
});
