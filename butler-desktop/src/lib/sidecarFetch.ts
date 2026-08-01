import { SIDECAR_BASE } from '../constants';
import { getSidecarCapabilityToken } from './connect_loop/sidecarAuth';

/**
 * 공통 sidecar fetch helper (박스1·2·5 공통 인증 계층).
 *
 * 배경: sidecar 는 POST/DELETE 에 capability token 을 요구한다(_capability_token_middleware).
 * token 이 없으면 401 을 반환하는데, 그 401 은 CORS 미들웨어를 우회해 Access-Control-Allow-Origin
 * 헤더가 없으므로 WKWebView 가 "TypeError: Load failed" 로 떨군다(401 을 못 읽음). 따라서 모달이
 * 개별 fetch 로 token 을 빠뜨리면 박스1/2 가 모두 "Load failed" 가 된다.
 *
 * 이 helper 는:
 *  - POST/DELETE 에 Authorization: Bearer <token> 을 자동 첨부한다(GET 도 통과 가능).
 *  - token 미가용(CAPABILITY_TOKEN_EMPTY 등) 시 fetch 전에 fail-closed 로 throw 한다.
 *  - fetch 자체 실패(네트워크/Load failed)를 endpoint·method 를 보존한 SidecarFetchError 로 감싼다.
 *  - 보안: raw body/text/token 을 로그에 남기지 않는다(메시지에 method·path 만).
 *  - 응답 Response 를 그대로 반환한다(SSE/스트리밍·FormData·파일 다운로드 모두 호출부가 처리).
 */

export class SidecarFetchError extends Error {
  readonly endpoint: string;
  readonly method: string;
  readonly cause: unknown;
  constructor(endpoint: string, method: string, cause: unknown) {
    const detail = cause instanceof Error ? cause.message : 'network error';
    super(`sidecar 요청 실패 (${method} ${endpoint}): ${detail}`);
    this.name = 'SidecarFetchError';
    this.endpoint = endpoint;
    this.method = method;
    this.cause = cause;
  }
}

export class SidecarTargetError extends Error {
  constructor() {
    super('SIDECAR_TARGET_REJECTED');
    this.name = 'SidecarTargetError';
  }
}

export class SidecarDeadlineError extends Error {
  readonly code = 'SIDECAR_DEADLINE_EXCEEDED';

  constructor() {
    super('SIDECAR_DEADLINE_EXCEEDED');
    this.name = 'SidecarDeadlineError';
  }
}

export type DeadlineOptions = Readonly<{
  deadlineMs: number;
  externalSignal?: AbortSignal;
}>;

/**
 * Runs one complete caller-owned operation inside a finite deadline.
 *
 * This is deliberately opt-in: model execution, uploads and streaming have
 * different budgets and must not inherit a short global timeout. The race is
 * retained in addition to AbortController so adapters and test doubles that
 * ignore AbortSignal still cannot leave the caller pending forever.
 */
export async function withDeadline<T>(
  operation: (signal: AbortSignal) => Promise<T>,
  options: DeadlineOptions,
): Promise<T> {
  const { deadlineMs, externalSignal } = options;
  if (!Number.isSafeInteger(deadlineMs) || deadlineMs <= 0) {
    throw new TypeError('DEADLINE_MS_INVALID');
  }
  if (externalSignal?.aborted) {
    throw externalSignal.reason
      ?? new DOMException('External abort', 'AbortError');
  }

  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let removeExternalListener = () => {};

  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      const error = new SidecarDeadlineError();
      controller.abort(error);
      reject(error);
    }, deadlineMs);
  });

  const externalAbort = new Promise<never>((_, reject) => {
    if (!externalSignal) return;
    const abort = () => {
      const reason = externalSignal.reason
        ?? new DOMException('External abort', 'AbortError');
      controller.abort(reason);
      reject(reason);
    };
    if (externalSignal.aborted) {
      abort();
      return;
    }
    externalSignal.addEventListener('abort', abort, { once: true });
    removeExternalListener = () => {
      externalSignal.removeEventListener('abort', abort);
    };
  });

  try {
    return await Promise.race([
      operation(controller.signal),
      deadline,
      externalAbort,
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    removeExternalListener();
  }
}

function resolveSidecarTarget(path: string): URL {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) {
    throw new SidecarTargetError();
  }
  let target: URL;
  try {
    target = new URL(path, `${SIDECAR_BASE}/`);
  } catch {
    throw new SidecarTargetError();
  }
  const expected = new URL(SIDECAR_BASE);
  if (
    target.origin !== expected.origin
    || target.username !== ''
    || target.password !== ''
    || target.hash !== ''
  ) {
    throw new SidecarTargetError();
  }
  return target;
}

function toHeaderRecord(init?: HeadersInit): Record<string, string> {
  const out: Record<string, string> = {};
  if (!init) return out;
  if (init instanceof Headers) {
    init.forEach((value, key) => {
      out[key] = value;
    });
  } else if (Array.isArray(init)) {
    for (const [key, value] of init) out[key] = value;
  } else {
    Object.assign(out, init);
  }
  return out;
}

export async function sidecarFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? 'GET').toUpperCase();
  const target = resolveSidecarTarget(path);
  const endpoint = target.pathname;
  // headers 는 plain object 로 유지한다(기존 fetch 호출부·테스트와 동일 계약: headers.Authorization).
  const headers = toHeaderRecord(init.headers);

  // sidecar 는 POST/DELETE 에 token 을 요구한다. GET 도 helper 로 통일 시 동일하게 첨부한다
  // (앱은 항상 token 보유, 공개 GET 에 token 동반은 무해). token 미가용이면 fetch 전에 throw(fail-closed).
  const token = await getSidecarCapabilityToken();
  headers['Authorization'] = `Bearer ${token}`;

  try {
    return await fetch(target, { ...init, method, headers, redirect: 'error' });
  } catch (cause) {
    // fetch 자체 실패(TypeError: Load failed 등) — endpoint/method 보존, raw 미로깅.
    throw new SidecarFetchError(endpoint, method, cause);
  }
}

/** 모달 공통: helper/엔드포인트 오류를 사용자 표시용 메시지로 변환(원문/토큰 미노출). */
export function uiSafeSidecarErrorMessage(err: unknown): string {
  if (err instanceof Error) {
    if (err.message === 'CAPABILITY_TOKEN_EMPTY' || err.message.includes('capability')) {
      return 'sidecar 통신 권한 토큰을 가져오지 못했습니다. 앱을 재시작해 주세요.';
    }
    if (err instanceof SidecarFetchError || err.message.includes('Load failed') || err.name === 'TypeError') {
      return '로컬 sidecar 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.';
    }
  }
  return '요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.';
}
