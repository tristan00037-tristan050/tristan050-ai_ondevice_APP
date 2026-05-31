import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ChatUIBridge } from '../components/connect_loop/ChatUIBridge';
import {
  type RouterDecisionV1,
  assertLocalSidecarUrl,
  assertValidChatRequest,
  assertValidRouterDecision,
  createChatRequest,
  resolveCallableEndpoint,
} from '../lib/connect_loop/contracts';
import { runChatBridge } from '../lib/connect_loop/client';

const zeroDigest = `sha256:${'0'.repeat(64)}` as const;
const testDirname = dirname(fileURLToPath(import.meta.url));
const prdSourceFiles = [
  'components/connect_loop/ChatUIBridge.tsx',
  'components/connect_loop/SecurityBadges.tsx',
  'lib/connect_loop/client.ts',
  'lib/connect_loop/contracts.ts',
] as const;

async function stableHash(value: string): Promise<`sha256:${string}`> {
  const seed = Array.from(value).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return `sha256:${seed.toString(16).padStart(64, '0')}`;
}

function decision(overrides: Partial<RouterDecisionV1> = {}): RouterDecisionV1 {
  return {
    request_id: 'req-connect-loop-001',
    intent_label: 'draft_write',
    target_box_id: '3',
    target_endpoint: 'POST /v1/cards/3/draft',
    routing_confidence: 0.91,
    reason_code: 'INTENT_KEYWORD_MATCH',
    fallback_required: false,
    policy_precheck: 'allow',
    schema_version: 'router_decision.v1',
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('PR-D Chat UI Bridge contracts', () => {
  it('creates digest-only chat_request.v1', async () => {
    const request = await createChatRequest('새 초안 작성 요청', {
      hashText: stableHash,
      requestId: 'req-connect-loop-001',
      now: new Date('2026-05-30T00:00:00Z'),
    });

    assertValidChatRequest(request);
    expect(request.text_ref).toBe('device_local_only');
    expect(request.text_digest).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(Object.keys(request)).not.toContain(['raw', 'text'].join('_'));
  });

  it('fails closed on router_decision unknown field', () => {
    const tampered = { ...decision(), unexpected: true };
    expect(() => assertValidRouterDecision(tampered)).toThrow('ROUTER_DECISION_UNKNOWN_OR_MISSING_FIELD');
  });

  it('resolves callable endpoint through static allowlist only', () => {
    expect(resolveCallableEndpoint(decision())).toBe('http://127.0.0.1:8765/v1/cards/3/draft');
  });

  it('does not resolve non-allow policy to a box call', () => {
    const closed = decision({
      target_endpoint: 'none',
      fallback_required: true,
      policy_precheck: 'needs_review',
    });
    expect(resolveCallableEndpoint(closed)).toBeNull();
  });

  it('rejects non-local endpoint URLs', () => {
    expect(() => assertLocalSidecarUrl('https://example.invalid/v1/cards/3/draft')).toThrow('BLOCK_NON_LOCAL_SIDECAR_URL');
    expect(() => assertLocalSidecarUrl('http://localhost:8765/v1/cards/3/draft')).toThrow('BLOCK_NON_LOCAL_SIDECAR_URL');
  });

  it('blocks digest mismatch before router call', async () => {
    const request = await createChatRequest('정상 요청', {
      hashText: stableHash,
      requestId: 'req-connect-loop-001',
      now: new Date('2026-05-30T00:00:00Z'),
    });
    const fetcher = vi.fn();
    const result = await runChatBridge('변조된 요청', {
      hashText: stableHash,
      requestOverride: { ...request, text_digest: zeroDigest },
      fetcher,
    });

    expect(result.status).toBe('digest_mismatch');
    expect(result.displayText).toBe('요청 검증에 실패했습니다. 다시 입력해 주세요.');
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('runs allow flow through router then allowlisted box endpoint', async () => {
    const calls: string[] = [];
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      calls.push(url);
      const body = JSON.parse(String(init.body));
      if (url.endsWith('/v1/router/decide')) {
        return jsonResponse({ decision: { ...decision(), request_id: body.chat_request.request_id } });
      }
      return jsonResponse({
        draft: '새 상황에 맞춘 초안입니다.',
        integration_mode: 'real',
        usage_log_count: 1,
      });
    });

    const result = await runChatBridge('새 상황 보고서 초안 작성', { hashText: stableHash, fetcher });
    expect(result.status).toBe('executed');
    expect(result.displayText).toBe('새 상황에 맞춘 초안입니다.');
    expect(result.usageLogCount).toBe(1);
    expect(calls).toEqual([
      'http://127.0.0.1:8765/v1/router/decide',
      'http://127.0.0.1:8765/v1/cards/3/draft',
    ]);
  });

  it('does not call box endpoint for unknown intent', async () => {
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      return jsonResponse({
        decision: decision({
          request_id: body.chat_request.request_id,
          intent_label: 'unknown',
          target_box_id: 'none',
          target_endpoint: 'none',
          fallback_required: true,
          routing_confidence: 0.1,
          reason_code: 'LOW_CONFIDENCE_FALLBACK',
        }),
      });
    });

    const result = await runChatBridge('검토', { hashText: stableHash, fetcher });
    expect(result.status).toBe('fallback');
    expect(result.displayText).toBe('요청을 안전하게 분류하지 못했습니다. 더 구체화해 주세요.');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('does not call box endpoint for general_chat', async () => {
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      return jsonResponse({
        decision: decision({
          request_id: body.chat_request.request_id,
          intent_label: 'general_chat',
          target_box_id: 'chat',
          target_endpoint: 'none',
          fallback_required: true,
          routing_confidence: 0.8,
          reason_code: 'GENERAL_CHAT_NO_ENDPOINT',
        }),
      });
    });

    const result = await runChatBridge('안녕하세요', { hashText: stableHash, fetcher });
    expect(result.status).toBe('fallback');
    expect(result.displayText).toBe('일반 대화는 별도 실행 대상으로 등록되지 않았습니다.');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('does not call box endpoint for block policy', async () => {
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      return jsonResponse({
        decision: decision({
          request_id: body.chat_request.request_id,
          target_endpoint: 'none',
          fallback_required: true,
          policy_precheck: 'block',
          reason_code: 'POLICY_BLOCKED',
        }),
      });
    });

    const result = await runChatBridge('차단 대상 요청', { hashText: stableHash, fetcher });
    expect(result.status).toBe('policy_closed');
    expect(result.displayText).toBe('정책상 처리할 수 없는 요청입니다.');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('fails closed when router decision request_id does not match chat_request', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ decision: decision({ request_id: 'different-request-id' }) }));

    const result = await runChatBridge('새 상황 보고서 초안 작성', { hashText: stableHash, fetcher });
    expect(result.status).toBe('decision_invalid');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('keeps PR-D source free of persistent browser storage and token exposure', () => {
    const forbiddenTerms = ['local' + 'Storage', 'session' + 'Storage', 'indexed' + 'DB'];
    const tokenLeakPatterns = [/console\.log\s*\([^)]*token/i, /Storage[^;\n]*token/i];

    for (const file of prdSourceFiles) {
      const source = readFileSync(resolve(testDirname, '..', file), 'utf8');
      for (const term of forbiddenTerms) {
        expect(source, `${file} must not mention ${term}`).not.toContain(term);
      }
      for (const pattern of tokenLeakPatterns) {
        expect(source, `${file} must not expose tokens`).not.toMatch(pattern);
      }
    }
  });

  it('keeps PR-D source free of non-local network primitives', () => {
    const networkPatterns = [
      new RegExp('fet' + 'ch\\s*\\('),
      new RegExp('axi' + 'os\\.'),
      new RegExp('XML' + 'HttpRequest'),
      new RegExp('send' + 'Beacon'),
      new RegExp('Web' + 'Socket'),
    ];

    for (const file of prdSourceFiles) {
      const source = readFileSync(resolve(testDirname, '..', file), 'utf8');
      for (const pattern of networkPatterns) {
        expect(source, `${file} must use the local sidecar client boundary`).not.toMatch(pattern);
      }
    }
  });
});

describe('PR-D Chat UI Bridge component', () => {
  it('shows result, security badges, routing decision, and usage log evidence', async () => {
    const runBridge = vi.fn(async (): Promise<Awaited<ReturnType<typeof runChatBridge>>> => ({
      status: 'executed',
      displayText: '작성된 초안입니다.',
      chatRequest: await createChatRequest('초안 요청', {
        hashText: stableHash,
        requestId: 'req-connect-loop-001',
        now: new Date('2026-05-30T00:00:00Z'),
      }),
      decision: decision(),
      boxResponse: { draft: '작성된 초안입니다.' },
      requestId: 'req-connect-loop-001',
      usageLogCount: 1,
      integrationMode: 'real',
      rawSavedZero: true,
      externalSendZero: true,
    }));

    render(<ChatUIBridge runBridge={runBridge} />);
    fireEvent.change(screen.getByTestId('connect-loop-input'), {
      target: { value: '새 초안 작성' },
    });
    fireEvent.click(screen.getByTestId('connect-loop-send'));

    await waitFor(() => expect(screen.getByText('작성된 초안입니다.')).toBeInTheDocument());
    expect(screen.getByText('원문 미반출')).toBeInTheDocument();
    expect(screen.getByText('비로컬 전송 0')).toBeInTheDocument();
    expect(screen.getByText('정책: allow')).toBeInTheDocument();
    expect(screen.getByText('대상: 3')).toBeInTheDocument();
    expect(screen.getByText('usage_log 1건')).toBeInTheDocument();
    expect(screen.getByTestId('connect-loop-router-decision')).toHaveTextContent('POST /v1/cards/3/draft');
  });

  it('shows safe policy message without executing a box', async () => {
    const runBridge = vi.fn(async (): Promise<Awaited<ReturnType<typeof runChatBridge>>> => ({
      status: 'policy_closed',
      displayText: '정책 검토가 필요한 요청입니다. 관리자 확인 후 진행됩니다.',
      chatRequest: await createChatRequest('검토 필요 요청', {
        hashText: stableHash,
        requestId: 'req-connect-loop-002',
        now: new Date('2026-05-30T00:00:00Z'),
      }),
      decision: decision({
        target_endpoint: 'none',
        fallback_required: true,
        policy_precheck: 'needs_review',
      }),
      boxResponse: null,
      requestId: 'req-connect-loop-002',
      usageLogCount: null,
      integrationMode: null,
      rawSavedZero: true,
      externalSendZero: true,
    }));

    render(<ChatUIBridge runBridge={runBridge} />);
    fireEvent.change(screen.getByTestId('connect-loop-input'), {
      target: { value: '정책 검토 필요 요청' },
    });
    fireEvent.keyDown(screen.getByTestId('connect-loop-input'), { key: 'Enter', shiftKey: false });

    await waitFor(() => expect(screen.getByText('정책 검토가 필요한 요청입니다. 관리자 확인 후 진행됩니다.')).toBeInTheDocument());
    expect(screen.getByText('정책: needs_review')).toBeInTheDocument();
    expect(screen.getByText('안전 처리됨')).toBeInTheDocument();
  });
});
