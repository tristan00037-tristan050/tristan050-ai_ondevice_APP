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
  const url = path.startsWith('http') ? path : `${SIDECAR_BASE}${path}`;
  // headers 는 plain object 로 유지한다(기존 fetch 호출부·테스트와 동일 계약: headers.Authorization).
  const headers = toHeaderRecord(init.headers);

  // sidecar 는 POST/DELETE 에 token 을 요구한다. GET 도 helper 로 통일 시 동일하게 첨부한다
  // (앱은 항상 token 보유, 공개 GET 에 token 동반은 무해). token 미가용이면 fetch 전에 throw(fail-closed).
  const token = await getSidecarCapabilityToken();
  headers['Authorization'] = `Bearer ${token}`;

  try {
    return await fetch(url, { ...init, method, headers });
  } catch (cause) {
    // fetch 자체 실패(TypeError: Load failed 등) — endpoint/method 보존, raw 미로깅.
    throw new SidecarFetchError(path, method, cause);
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
