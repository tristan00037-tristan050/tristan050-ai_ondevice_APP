import {
  ROUTER_DECIDE_URL,
  type ChatRequestV1,
  type RouterDecisionV1,
  assertLocalSidecarUrl,
  assertValidRouterDecision,
  createChatRequest,
  resolveCallableEndpoint,
  sha256TextDigest,
  verifyChatRequestDigest,
} from './contracts';

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

export type BridgeStatus =
  | 'executed'
  | 'fallback'
  | 'policy_closed'
  | 'digest_mismatch'
  | 'decision_invalid'
  | 'endpoint_failed';

export interface ChatBridgeResult {
  status: BridgeStatus;
  displayText: string;
  chatRequest: ChatRequestV1;
  decision: RouterDecisionV1 | null;
  boxResponse: unknown;
  requestId: string;
  usageLogCount: number | null;
  integrationMode: string | null;
  rawSavedZero: true;
  externalSendZero: true;
}

export interface RunChatBridgeOptions {
  fetcher?: FetchLike;
  timeoutMs?: number;
  requestOverride?: ChatRequestV1;
  hashText?: (value: string) => Promise<`sha256:${string}`>;
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get('Content-Type') ?? '';
  if (!contentType.includes('application/json')) {
    return {};
  }
  return response.json() as Promise<unknown>;
}

async function postLocalJson(
  url: string,
  body: JsonValue,
  options: { fetcher?: FetchLike; timeoutMs?: number } = {},
): Promise<unknown> {
  assertLocalSidecarUrl(url);
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), options.timeoutMs ?? 30_000);
  const activeFetch = options.fetcher ?? globalThis.fetch.bind(globalThis);
  try {
    const response = await activeFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`LOCAL_SIDECAR_HTTP_${response.status}`);
    }
    return await readJson(response);
  } finally {
    clearTimeout(timeoutHandle);
  }
}

function extractDecision(payload: unknown): unknown {
  if (typeof payload === 'object' && payload !== null && 'decision' in payload) {
    return (payload as { decision: unknown }).decision;
  }
  return payload;
}

function extractDisplayText(payload: unknown): string {
  if (typeof payload === 'object' && payload !== null) {
    const record = payload as Record<string, unknown>;
    for (const key of ['answer', 'draft', 'result', 'message', 'rewritten_doc']) {
      if (typeof record[key] === 'string' && record[key].trim()) {
        return record[key];
      }
    }
  }
  return '요청이 처리되었습니다.';
}

function extractUsageLogCount(payload: unknown): number | null {
  if (typeof payload !== 'object' || payload === null) return null;
  const record = payload as Record<string, unknown>;
  if (typeof record.usage_log_count === 'number') return record.usage_log_count;
  if (Array.isArray(record.usage_logs)) return record.usage_logs.length;
  if (record.usage_log_created === true) return 1;
  return null;
}

function extractIntegrationMode(payload: unknown): string | null {
  if (typeof payload !== 'object' || payload === null) return null;
  const record = payload as Record<string, unknown>;
  return typeof record.integration_mode === 'string' ? record.integration_mode : null;
}

export function fallbackMessage(decision: RouterDecisionV1 | null, status: BridgeStatus): string {
  if (status === 'digest_mismatch') return '요청 검증에 실패했습니다. 다시 입력해 주세요.';
  if (status === 'decision_invalid') return '요청 라우팅 검증에 실패했습니다. 다시 입력해 주세요.';
  if (status === 'endpoint_failed') return '실행에 실패했습니다. 다시 시도하거나 문의해 주세요.';
  if (!decision) return '요청을 안전하게 처리하지 못했습니다. 더 구체화해 주세요.';
  if (decision.policy_precheck === 'needs_review') return '정책 검토가 필요한 요청입니다. 관리자 확인 후 진행됩니다.';
  if (decision.policy_precheck === 'block') return '정책상 처리할 수 없는 요청입니다.';
  if (decision.intent_label === 'general_chat') return '일반 대화는 별도 실행 대상으로 등록되지 않았습니다.';
  return '요청을 안전하게 분류하지 못했습니다. 더 구체화해 주세요.';
}

export async function runChatBridge(runtimeTextInput: string, options: RunChatBridgeOptions = {}): Promise<ChatBridgeResult> {
  let runtimeText: string | null = runtimeTextInput.trim();
  const hashText = options.hashText ?? sha256TextDigest;
  const chatRequest = options.requestOverride ?? await createChatRequest(runtimeText, { hashText });
  try {
    const digestMatches = await verifyChatRequestDigest(runtimeText, chatRequest, hashText);
    if (!digestMatches) {
      return {
        status: 'digest_mismatch',
        displayText: fallbackMessage(null, 'digest_mismatch'),
        chatRequest,
        decision: null,
        boxResponse: null,
        requestId: chatRequest.request_id,
        usageLogCount: null,
        integrationMode: null,
        rawSavedZero: true,
        externalSendZero: true,
      };
    }

    const routerPayload = {
      chat_request: chatRequest,
      runtime: { runtime_text: runtimeText },
    };
    const routerPayloadJson = routerPayload as unknown as JsonValue;
    const routerResponse = await postLocalJson(ROUTER_DECIDE_URL, routerPayloadJson, options);
    const decisionCandidate = extractDecision(routerResponse);
    try {
      assertValidRouterDecision(decisionCandidate);
      if (decisionCandidate.request_id !== chatRequest.request_id) {
        throw new Error('ROUTER_DECISION_REQUEST_ID_MISMATCH');
      }
    } catch {
      return {
        status: 'decision_invalid',
        displayText: fallbackMessage(null, 'decision_invalid'),
        chatRequest,
        decision: null,
        boxResponse: null,
        requestId: chatRequest.request_id,
        usageLogCount: null,
        integrationMode: null,
        rawSavedZero: true,
        externalSendZero: true,
      };
    }

    const decision = decisionCandidate;
    const callableUrl = resolveCallableEndpoint(decision);
    if (!callableUrl) {
      const status: BridgeStatus = decision.policy_precheck === 'allow' ? 'fallback' : 'policy_closed';
      return {
        status,
        displayText: fallbackMessage(decision, status),
        chatRequest,
        decision,
        boxResponse: null,
        requestId: chatRequest.request_id,
        usageLogCount: null,
        integrationMode: null,
        rawSavedZero: true,
        externalSendZero: true,
      };
    }

    const boxPayload = {
      chat_request: chatRequest,
      router_decision: decision,
      runtime: { runtime_text: runtimeText },
    };
    const boxResponse = await postLocalJson(callableUrl, boxPayload as unknown as JsonValue, options);
    return {
      status: 'executed',
      displayText: extractDisplayText(boxResponse),
      chatRequest,
      decision,
      boxResponse,
      requestId: chatRequest.request_id,
      usageLogCount: extractUsageLogCount(boxResponse),
      integrationMode: extractIntegrationMode(boxResponse),
      rawSavedZero: true,
      externalSendZero: true,
    };
  } catch {
    return {
      status: 'endpoint_failed',
      displayText: fallbackMessage(null, 'endpoint_failed'),
      chatRequest,
      decision: null,
      boxResponse: null,
      requestId: chatRequest.request_id,
      usageLogCount: null,
      integrationMode: null,
      rawSavedZero: true,
      externalSendZero: true,
    };
  } finally {
    runtimeText = null;
  }
}
