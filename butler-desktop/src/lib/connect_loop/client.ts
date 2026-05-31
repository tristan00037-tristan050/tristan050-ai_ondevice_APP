import {
  ROUTER_DECIDE_URL,
  type ChatRequestV1,
  type IntentLabel,
  type RouterDecisionV1,
  assertLocalSidecarUrl,
  assertValidChatRequest,
  assertValidRouterDecision,
  createChatRequest,
  resolveCallableEndpoint,
  sha256TextDigest,
  verifyChatRequestDigest,
} from './contracts';
import { getSidecarCapabilityToken, type CapabilityTokenProvider } from './sidecarAuth';

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
type FetchLike = (input: string, init: RequestInit) => Promise<Response>;
type HeaderMap = Record<string, string>;

export type BridgeStatus =
  | 'executed'
  | 'fallback'
  | 'policy_closed'
  | 'digest_mismatch'
  | 'decision_invalid'
  | 'endpoint_failed'
  | 'payload_missing'
  | 'security_blocked';

// 메인팀 v1.3: usage_log 독립 검증 결과. 미구성은 PASS 가 아니라 'not_configured'(거짓 PASS 금지).
export type UsageLogVerification = 'verified' | 'missing' | 'not_configured';

// request_id 기준 usage_log 건수를 독립적으로 확인하는 주입 경계.
export type UsageLogVerifier = (requestId: string) => Promise<number | null>;

export interface BoxRuntimeInputs {
  foreignDoc?: string;
  ourFormat?: string;
  promptTemplate?: string;
  maxNewTokens?: number;
  topK?: number;
}

export interface ChatBridgeResult {
  status: BridgeStatus;
  displayText: string;
  chatRequest: ChatRequestV1;
  decision: RouterDecisionV1 | null;
  boxResponse: unknown;
  requestId: string;
  usageLogCount: number | null;
  usageLogVerification: UsageLogVerification;
  integrationMode: string | null;
  rawSavedZero: true;
  externalSendZero: true;
}

export interface RunChatBridgeOptions {
  fetcher?: FetchLike;
  timeoutMs?: number;
  requestOverride?: ChatRequestV1;
  hashText?: (value: string) => Promise<`sha256:${string}`>;
  capabilityTokenProvider?: CapabilityTokenProvider;
  boxInputs?: BoxRuntimeInputs;
  // 주입 시 request_id 로 usage_log 1건 이상을 독립 확인. 미주입 시 'not_configured'.
  usageLogVerifier?: UsageLogVerifier;
}

export const DEFAULT_BOX3_PROMPT_TEMPLATE =
  '과거 문서 안의 근거만 사용해 새 상황의 초안을 작성하세요. 불명확한 내용은 [확인 필요]로 표시하세요.' as const;

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
  options: { fetcher?: FetchLike; timeoutMs?: number; authToken: string; extraHeaders?: HeaderMap },
): Promise<unknown> {
  assertLocalSidecarUrl(url);
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), options.timeoutMs ?? 30_000);
  const activeFetch = options.fetcher ?? globalThis.fetch.bind(globalThis);
  const headers: HeaderMap = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${options.authToken}`,
    ...(options.extraHeaders ?? {}),
  };
  try {
    const response = await activeFetch(url, {
      method: 'POST',
      headers,
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

export function buildTargetBoxPayload(
  decision: Pick<RouterDecisionV1, 'intent_label'>,
  runtimeText: string,
  inputs: BoxRuntimeInputs = {},
): JsonValue | null {
  const intent = decision.intent_label as IntentLabel;
  if (intent === 'memory_search') {
    return {
      query: runtimeText,
      top_k: inputs.topK ?? 5,
    };
  }
  if (intent === 'form_convert') {
    const foreignDoc = inputs.foreignDoc?.trim();
    const ourFormat = inputs.ourFormat?.trim();
    if (!foreignDoc || !ourFormat) return null;
    return {
      foreign_doc: foreignDoc,
      our_format: ourFormat,
      options: {
        tone: 'company_standard',
        preserve_numbers: true,
        redact_sensitive: true,
      },
    };
  }
  if (intent === 'draft_write') {
    return {
      input_text: runtimeText,
      prompt_template: inputs.promptTemplate?.trim() || DEFAULT_BOX3_PROMPT_TEMPLATE,
      max_new_tokens: inputs.maxNewTokens ?? 512,
    };
  }
  return null;
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
    // Codex P2: Box3 실제 응답(DraftResult.to_dict())은 'draft_text' 키를 사용한다.
    for (const key of ['answer', 'draft_text', 'draft', 'result', 'message', 'rewritten_doc']) {
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

/**
 * 메인팀 v1.3: box response 의 보안 플래그를 affirmative 하게 확인한다.
 * external_send_zero 가 명시적으로 true 가 아니거나(누락 포함), raw_text_logged/raw_doc_logged
 * 가 true 면 안전을 입증하지 못한 것이므로 결과 표시를 차단한다(배지가 안전한 것처럼 보이는 것 방지).
 */
export function validateBoxResponseSecurity(response: unknown): boolean {
  if (typeof response !== 'object' || response === null) return false;
  const record = response as Record<string, unknown>;
  if (record.external_send_zero !== true) return false;
  // raw 로깅 플래그가 true 면 차단.
  if (record.raw_text_logged === true || record.raw_doc_logged === true) return false;
  // Codex P1: raw 로깅 플래그 누락은 '입증되지 않은' 보안이므로 fail-closed.
  // 최소 하나의 raw-log 플래그가 명시적으로 false 여야 통과(빈/부분 응답 차단).
  const explicitRawFalse = record.raw_text_logged === false || record.raw_doc_logged === false;
  if (!explicitRawFalse) return false;
  return true;
}

/**
 * 메인팀 v1.3: usage_log 독립 검증. verifier 미주입 시 'not_configured'(거짓 PASS 금지).
 * 주입 시 request_id 기준 1건 이상이면 'verified', 아니면 'missing'.
 */
async function verifyUsageLog(
  requestId: string,
  verifier: UsageLogVerifier | undefined,
): Promise<UsageLogVerification> {
  if (!verifier) return 'not_configured';
  try {
    const count = await verifier(requestId);
    return typeof count === 'number' && count >= 1 ? 'verified' : 'missing';
  } catch {
    return 'missing';
  }
}

export function fallbackMessage(decision: RouterDecisionV1 | null, status: BridgeStatus): string {
  if (status === 'security_blocked') return '응답 보안 검증에 실패하여 결과를 표시하지 않습니다.';
  if (status === 'digest_mismatch') return '요청 검증에 실패했습니다. 다시 입력해 주세요.';
  if (status === 'decision_invalid') return '요청 라우팅 검증에 실패했습니다. 다시 입력해 주세요.';
  if (status === 'endpoint_failed') return '실행에 실패했습니다. 다시 시도하거나 문의해 주세요.';
  if (status === 'payload_missing') return '실행에 필요한 입력이 부족하여 박스를 호출하지 않았습니다.';
  if (!decision) return '요청을 안전하게 처리하지 못했습니다. 더 구체화해 주세요.';
  if (decision.policy_precheck === 'needs_review') return '정책 검토가 필요한 요청입니다. 관리자 확인 후 진행됩니다.';
  if (decision.policy_precheck === 'block') return '정책상 처리할 수 없는 요청입니다.';
  if (decision.intent_label === 'general_chat') return '일반 대화는 별도 실행 대상으로 등록되지 않았습니다.';
  return '요청을 안전하게 분류하지 못했습니다. 더 구체화해 주세요.';
}

export async function runChatBridge(runtimeTextInput: string, options: RunChatBridgeOptions = {}): Promise<ChatBridgeResult> {
  let runtimeText: string | null = runtimeTextInput.trim();
  const hashText = options.hashText ?? sha256TextDigest;
  // Codex P2: requestOverride 도 createChatRequest 와 동일한 fail-closed 스키마/첨부 가드를 거친다
  // (override 가 검증을 우회해 schema drift·첨부 초과 등이 라우터로 전송되는 것 차단).
  const chatRequest = options.requestOverride ?? await createChatRequest(runtimeText, { hashText });
  if (options.requestOverride) {
    assertValidChatRequest(chatRequest);
  }
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
        usageLogVerification: 'not_configured',
        integrationMode: null,
        rawSavedZero: true,
        externalSendZero: true,
      };
    }

    const authToken = await (options.capabilityTokenProvider ?? getSidecarCapabilityToken)();
    const routerPayload = {
      chat_request: chatRequest,
      runtime: { runtime_text: runtimeText },
    };
    const routerPayloadJson = routerPayload as unknown as JsonValue;
    const routerResponse = await postLocalJson(ROUTER_DECIDE_URL, routerPayloadJson, {
      fetcher: options.fetcher,
      timeoutMs: options.timeoutMs,
      authToken,
    });
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
        usageLogVerification: 'not_configured',
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
        usageLogVerification: 'not_configured',
        integrationMode: null,
        rawSavedZero: true,
        externalSendZero: true,
      };
    }

    const boxPayload = buildTargetBoxPayload(decision, runtimeText, options.boxInputs);
    if (!boxPayload) {
      return {
        status: 'payload_missing',
        displayText: fallbackMessage(decision, 'payload_missing'),
        chatRequest,
        decision,
        boxResponse: null,
        requestId: chatRequest.request_id,
        usageLogCount: null,
        usageLogVerification: 'not_configured',
        integrationMode: null,
        rawSavedZero: true,
        externalSendZero: true,
      };
    }
    const boxResponse = await postLocalJson(callableUrl, boxPayload, {
      fetcher: options.fetcher,
      timeoutMs: options.timeoutMs,
      authToken,
      extraHeaders: {
        'x-request-id': chatRequest.request_id,
        'x-routing-confidence': String(decision.routing_confidence),
        'x-learning-candidate': '0',
      },
    });

    // 메인팀 v1.3: box response 보안 플래그 미입증 시 결과 표시 차단(security_blocked).
    if (!validateBoxResponseSecurity(boxResponse)) {
      return {
        status: 'security_blocked',
        displayText: fallbackMessage(null, 'security_blocked'),
        chatRequest,
        decision,
        boxResponse: null,
        requestId: chatRequest.request_id,
        usageLogCount: null,
        usageLogVerification: 'not_configured',
        integrationMode: null,
        rawSavedZero: true,
        externalSendZero: true,
      };
    }

    // 메인팀 v1.3: usage_log 독립 검증(미주입 시 not_configured — 거짓 PASS 금지).
    const usageLogVerification = await verifyUsageLog(chatRequest.request_id, options.usageLogVerifier);

    return {
      status: 'executed',
      displayText: extractDisplayText(boxResponse),
      chatRequest,
      decision,
      boxResponse,
      requestId: chatRequest.request_id,
      usageLogCount: extractUsageLogCount(boxResponse),
      usageLogVerification,
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
      usageLogVerification: 'not_configured',
      integrationMode: null,
      rawSavedZero: true,
      externalSendZero: true,
    };
  } finally {
    runtimeText = null;
  }
}
