/**
 * HUD에서 BFF 호출용 최소 API 래퍼
 * Idempotency / Role 헤더 포함
 * 
 * @module app-expo/hud/accounting-api
 */

// crypto.randomUUID() polyfill for environments without Web Crypto API
function randomUUID(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for Node.js environments
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

type HeadersInitLike = Record<string, string>;

export type ClientCfg = {
  baseUrl: string;
  tenantId: string;
  apiKey: string;
};

export function mkHeaders(cfg: ClientCfg, extra?: HeadersInitLike): HeadersInitLike {
  return {
    'Content-Type': 'application/json',
    'X-Tenant': cfg.tenantId,
    'X-Api-Key': cfg.apiKey,
    ...(extra ?? {}),
  };
}

async function mkUUID(): Promise<string> {
  // RN/Expo 환경에서 crypto.randomUUID 부재 시 expo-random로 대체
  // @ts-ignore
  if (globalThis?.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  const { getRandomBytesAsync } = await import('expo-random');
  const b = await getRandomBytesAsync(16);
  // RFC4122 v4 포맷팅
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const hex = [...b].map(x => x.toString(16).padStart(2, '0'));
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10, 16).join('')}`;
}

type IdemOpts = { idem?: string };

// fetch polyfill for Node.js environments (if needed)
declare const fetch: typeof globalThis.fetch;

/**
 * 분개 추천 요청
 */
export async function postSuggest(cfg: ClientCfg, body: any, opts?: IdemOpts) {
  const r = await fetch(`${cfg.baseUrl}/v1/accounting/postings/suggest`, {
    method: 'POST',
    headers: mkHeaders(cfg, { 'Idempotency-Key': opts?.idem ?? await mkUUID() }),
    body: JSON.stringify(body),
  });
  
  if (!r.ok) {
    throw new Error(`suggest ${r.status}`);
  }
  
  return r.json();
}

/**
 * 승인 요청
 */
export async function postApproval(
  cfg: ClientCfg, 
  id: string, 
  action: 'approve' | 'reject', 
  note?: string, 
  opts?: IdemOpts & {
    top1_selected?: boolean;
    selected_rank?: number;
    ai_score?: number;
  }
) {
  const body: any = { 
    action, 
    client_request_id: await mkUUID(), 
    note 
  };
  
  // 선택 정보 추가 (approve 액션일 때만)
  if (action === 'approve' && opts) {
    if (opts.top1_selected !== undefined) {
      body.top1_selected = opts.top1_selected;
    }
    if (opts.selected_rank !== undefined) {
      body.selected_rank = opts.selected_rank;
    }
    if (opts.ai_score !== undefined) {
      body.ai_score = opts.ai_score;
    }
  }
  
  const r = await fetch(`${cfg.baseUrl}/v1/accounting/approvals/${id}`, {
    method: 'POST',
    headers: mkHeaders(cfg, { 'Idempotency-Key': opts?.idem ?? await mkUUID() }),
    body: JSON.stringify(body),
  });
  
  if (!r.ok) {
    throw new Error(`approval ${r.status}`);
  }
  
  return r.json();
}

/**
 * Export 잡 생성
 */
export async function postExport(cfg: ClientCfg, body: any, opts?: IdemOpts) {
  const r = await fetch(`${cfg.baseUrl}/v1/accounting/exports/reports`, {
    method: 'POST',
    headers: mkHeaders(cfg, { 'Idempotency-Key': opts?.idem ?? await mkUUID() }),
    body: JSON.stringify(body),
  });
  
  if (!r.ok) {
    throw new Error(`export ${r.status}`);
  }
  
  return r.json();
}

/**
 * Export 잡 상태 조회
 */
export async function getExport(cfg: ClientCfg, jobId: string) {
  const r = await fetch(`${cfg.baseUrl}/v1/accounting/exports/${jobId}`, {
    headers: mkHeaders(cfg),
  });
  
  if (!r.ok) {
    throw new Error(`export get ${r.status}`);
  }
  
  return r.json();
}

/**
 * 대사 세션 생성
 */
export async function postReconCreate(cfg: ClientCfg, body: any, opts?: IdemOpts) {
  const r = await fetch(`${cfg.baseUrl}/v1/accounting/reconciliation/sessions`, {
    method: 'POST',
    headers: mkHeaders(cfg, { 'Idempotency-Key': opts?.idem ?? await mkUUID() }),
    body: JSON.stringify(body),
  });
  
  if (!r.ok) {
    throw new Error(`recon create ${r.status}`);
  }
  
  return r.json();
}

/**
 * 수동 매칭 적용
 */
export async function postReconMatch(cfg: ClientCfg, sessionId: string, bank_id: string, ledger_id: string, opts?: IdemOpts) {
  const r = await fetch(`${cfg.baseUrl}/v1/accounting/reconciliation/sessions/${sessionId}/match`, {
    method: 'POST',
    headers: mkHeaders(cfg, { 'Idempotency-Key': opts?.idem ?? await mkUUID() }),
    body: JSON.stringify({ bank_id, ledger_id }),
  });
  
  if (!r.ok) {
    throw new Error(`recon match ${r.status}`);
  }
  
  return r.json();
}

/**
 * 대사 세션 조회
 */
export async function getRecon(cfg: ClientCfg, sessionId: string) {
  const r = await fetch(`${cfg.baseUrl}/v1/accounting/reconciliation/sessions/${sessionId}`, {
    headers: mkHeaders(cfg),
  });
  
  if (!r.ok) {
    throw new Error(`recon get ${r.status}`);
  }
  
  return r.json();
}

