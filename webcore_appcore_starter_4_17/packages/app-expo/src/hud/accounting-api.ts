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

export type Mode = 'live' | 'mock';

export type SuggestEngineMode = 'local' | 'remote';

export interface SuggestItem {
  id: string;
  account?: string;
  amount: number;
  currency: string;
  vendor?: string;
  description?: string;
  rationale?: string;
  score?: number;
  risk?: {
    level: 'LOW' | 'MEDIUM' | 'HIGH';
    reasons: string[];
    score: number;
  };
}

export interface SuggestEngine {
  mode: SuggestEngineMode;
  suggest(input: {
    description: string;
    amount?: number;
    currency?: string;
  }): Promise<SuggestItem[]>;
}

export interface ClientCfg {
  baseUrl: string;
  tenantId: string;
  apiKey: string;
  mode?: Mode;  // 옵션이지만, App.tsx에서 항상 넣어줌
}

/**
 * API 에러 타입
 */
export interface ApiError {
  kind: 'client' | 'server' | 'network';
  status?: number;
  message: string;
  details?: any;
}

/**
 * Mock 모드 판정 유틸
 * 환경변수 백업 체크까지 포함 (빌드타임)
 */
export function isMock(cfg: ClientCfg): boolean {
  // 환경변수 백업 체크까지 (빌드타임)
  if (process.env.EXPO_PUBLIC_DEMO_MODE === 'mock') return true;
  return cfg.mode === 'mock';
}

export function mkHeaders(cfg: ClientCfg, extra?: HeadersInitLike): HeadersInitLike {
  const base: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Tenant': cfg.tenantId,
    'X-Api-Key': cfg.apiKey,
  };

  // API 키에서 role 추출 (collector-key:operator → operator)
  const role = cfg.apiKey.includes(':') ? cfg.apiKey.split(':')[1] : 'operator';
  base['X-User-Role'] = role;
  base['X-User-Id'] = 'hud-user-1';

  return { ...base, ...(extra || {}) };
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

// Mock 응답 데이터
const MOCK_SUGGEST_RESPONSE = {
  postings: [
    { id: 'p1', account: '5100', amount: '4500', currency: 'KRW', desc: '커피', score: 0.95 },
    { id: 'p2', account: '5200', amount: '4500', currency: 'KRW', desc: '음료', score: 0.85 },
    { id: 'p3', account: '5300', amount: '4500', currency: 'KRW', desc: '간식', score: 0.75 },
  ],
  rationale: '커피 영수증에 대한 추천 결과입니다.',
};

/**
 * 로컬 규칙 기반 Suggest 엔진 (온디바이스)
 * 나중에 실제 LLM/Classifier로 교체 가능
 */
const localRuleEngineV1: SuggestEngine = {
  mode: 'local',
  async suggest(input: { description: string; amount?: number; currency?: string }): Promise<SuggestItem[]> {
    // 간단한 규칙 기반 분류
    const desc = input.description.toLowerCase();
    const amount = input.amount || 0;
    const currency = input.currency || 'KRW';
    
    const items: SuggestItem[] = [];
    
    // 커피/음료 관련
    if (desc.includes('커피') || desc.includes('스타벅스') || desc.includes('카페')) {
      items.push({
        id: 'local-p1',
        account: '5100',
        amount,
        currency,
        vendor: '스타벅스',
        description: desc,
        rationale: '커피/음료 비용으로 분류됨 (온디바이스 규칙)',
        score: 0.92,
        risk: {
          level: amount >= 1000000 ? 'HIGH' : amount >= 500000 ? 'MEDIUM' : 'LOW',
          reasons: amount >= 1000000 ? ['HIGH_VALUE'] : amount >= 500000 ? ['MEDIUM_VALUE'] : [],
          score: amount >= 1000000 ? 85 : amount >= 500000 ? 50 : 10,
        },
      });
    }
    
    // 택시/교통비
    if (desc.includes('택시') || desc.includes('교통')) {
      items.push({
        id: 'local-p2',
        account: '5200',
        amount,
        currency,
        vendor: '택시',
        description: desc,
        rationale: '교통비로 분류됨 (온디바이스 규칙)',
        score: 0.88,
        risk: {
          level: amount >= 1000000 ? 'HIGH' : amount >= 500000 ? 'MEDIUM' : 'LOW',
          reasons: amount >= 1000000 ? ['HIGH_VALUE'] : amount >= 500000 ? ['MEDIUM_VALUE'] : [],
          score: amount >= 1000000 ? 85 : amount >= 500000 ? 50 : 10,
        },
      });
    }
    
    // 기본 분류 (매칭되지 않으면 일반 비용)
    if (items.length === 0) {
      items.push({
        id: 'local-p-default',
        account: '5300',
        amount,
        currency,
        vendor: '기타',
        description: desc,
        rationale: '일반 비용으로 분류됨 (온디바이스 규칙)',
        score: 0.70,
        risk: {
          level: amount >= 1000000 ? 'HIGH' : amount >= 500000 ? 'MEDIUM' : 'LOW',
          reasons: amount >= 1000000 ? ['HIGH_VALUE'] : amount >= 500000 ? ['MEDIUM_VALUE'] : [],
          score: amount >= 1000000 ? 85 : amount >= 500000 ? 50 : 10,
        },
      });
    }
    
    // 고액 거래 Mock 항목 추가 (항상 HIGH 표시)
    if (amount >= 1000000) {
      items.push({
        id: 'local-p-high',
        account: '5400',
        amount: amount,
        currency,
        vendor: '대형 장비 구매',
        description: desc,
        rationale: '고액 거래 - 수동 검토 필요 (온디바이스 규칙)',
        score: 0.75,
        risk: {
          level: 'HIGH',
          reasons: ['HIGH_VALUE'],
          score: 90,
        },
      });
    }
    
    return items;
  },
};

/**
 * Remote Suggest 엔진 (BFF 호출)
 */
const remoteEngine: SuggestEngine = {
  mode: 'remote',
  async suggest(input: { description: string; amount?: number; currency?: string }): Promise<SuggestItem[]> {
    // BFF 호출은 postSuggest 함수에서 처리
    // 여기서는 인터페이스만 정의
    throw new Error('Remote engine should use postSuggest function directly');
  },
};

/**
 * Suggest 엔진 선택 유틸
 */
export function getSuggestEngine(cfg: ClientCfg): SuggestEngine {
  if (isMock(cfg)) {
    return localRuleEngineV1;
  }
  
  // EXPO_PUBLIC_SUGGEST_ENGINE=local 이면 로컬 엔진 강제
  if (typeof process !== 'undefined' && process.env?.EXPO_PUBLIC_SUGGEST_ENGINE === 'local') {
    return localRuleEngineV1;
  }
  
  // 브라우저 환경에서도 체크
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('engine') === 'local') {
      return localRuleEngineV1;
    }
  }
  
  return remoteEngine;
}

const MOCK_APPROVAL_RESPONSE = { success: true, message: '승인 완료(모의)' };
const MOCK_EXPORT_RESPONSE = { jobId: 'export-mock-1', status: 'pending' };
const MOCK_RECON_CREATE_RESPONSE = { sessionId: 'recon-mock-1', status: 'open' };
const MOCK_RECON_MATCH_RESPONSE = { success: true, matched: true };

/**
 * 분개 추천 요청
 */
export async function postSuggest(cfg: ClientCfg, body: any, opts?: IdemOpts) {
  const engine = getSuggestEngine(cfg);
  
  // 로컬 엔진 사용 시
  if (engine.mode === 'local') {
    console.log('[LOCAL ENGINE] postSuggest:', body);
    const input = {
      description: body.items?.[0]?.description || body.description || '',
      amount: parseFloat(body.items?.[0]?.amount || body.amount || '0'),
      currency: body.items?.[0]?.currency || body.currency || 'KRW',
    };
    
    const items = await engine.suggest(input);
    await new Promise(resolve => setTimeout(resolve, 300)); // 시뮬레이션 지연
    
    return { items };
  }
  
  // Mock 모드 (로컬 엔진 사용)
  if (isMock(cfg)) {
    console.log('[MOCK] postSuggest:', body);
    const input = {
      description: body.items?.[0]?.description || body.description || '',
      amount: parseFloat(body.items?.[0]?.amount || body.amount || '4500'),
      currency: body.items?.[0]?.currency || body.currency || 'KRW',
    };
    
    const items = await localRuleEngineV1.suggest(input);
    await new Promise(resolve => setTimeout(resolve, 300));
    
    return { items };
  }

  try {
    const r = await fetch(`${cfg.baseUrl}/v1/accounting/postings/suggest`, {
      method: 'POST',
      headers: mkHeaders(cfg, { 'Idempotency-Key': opts?.idem ?? await mkUUID() }),
      body: JSON.stringify(body),
    });
    
    if (!r.ok) {
      const errorText = await r.text().catch(() => '');
      const error: ApiError = {
        kind: r.status >= 400 && r.status < 500 ? 'client' : 'server',
        status: r.status,
        message: r.status === 403 ? '권한이 없습니다' : 
                 r.status === 404 ? '요청한 리소스를 찾을 수 없습니다' :
                 r.status === 500 ? '서버 오류가 발생했습니다' :
                 `요청 실패 (${r.status})`,
        details: errorText || undefined,
      };
      throw error;
    }
    
    return r.json();
  } catch (e: any) {
    // fetch 자체 실패 (네트워크 오류)
    if (e instanceof TypeError || e.message?.includes('fetch')) {
      const error: ApiError = {
        kind: 'network',
        message: '서버에 연결할 수 없습니다. 네트워크 상태를 확인해주세요.',
        details: e.message,
      };
      throw error;
    }
    // 이미 ApiError인 경우 그대로 throw
    throw e;
  }
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
  if (isMock(cfg)) {
    console.log('[MOCK] postApproval:', { id, action, note, opts });
    await new Promise(resolve => setTimeout(resolve, 200));
    return { ...MOCK_APPROVAL_RESPONSE, action, id };
  }

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
  
  try {
    const r = await fetch(`${cfg.baseUrl}/v1/accounting/approvals/${id}`, {
      method: 'POST',
      headers: mkHeaders(cfg, { 'Idempotency-Key': opts?.idem ?? await mkUUID() }),
      body: JSON.stringify(body),
    });
    
    if (!r.ok) {
      const errorText = await r.text().catch(() => '');
      const error: ApiError = {
        kind: r.status >= 400 && r.status < 500 ? 'client' : 'server',
        status: r.status,
        message: r.status === 403 ? '승인 권한이 없습니다' : 
                 r.status === 404 ? '승인 대상을 찾을 수 없습니다' :
                 r.status === 500 ? '서버 오류가 발생했습니다' :
                 `승인 요청 실패 (${r.status})`,
        details: errorText || undefined,
      };
      throw error;
    }
    
    return r.json();
  } catch (e: any) {
    if (e instanceof TypeError || e.message?.includes('fetch')) {
      const error: ApiError = {
        kind: 'network',
        message: '서버에 연결할 수 없습니다',
        details: e.message,
      };
      throw error;
    }
    throw e;
  }
}

/**
 * Export 잡 생성
 */
export async function postExport(cfg: ClientCfg, body: any, opts?: IdemOpts) {
  if (isMock(cfg)) {
    console.log('[MOCK] postExport:', body);
    await new Promise(resolve => setTimeout(resolve, 200));
    return { jobId: 'export-mock-1', status: 'queued' };
  }

  try {
    const r = await fetch(`${cfg.baseUrl}/v1/accounting/exports/reports`, {
      method: 'POST',
      headers: mkHeaders(cfg, { 'Idempotency-Key': opts?.idem ?? await mkUUID() }),
      body: JSON.stringify(body),
    });
    
    if (!r.ok) {
      const errorText = await r.text().catch(() => '');
      const error: ApiError = {
        kind: r.status >= 400 && r.status < 500 ? 'client' : 'server',
        status: r.status,
        message: r.status === 403 ? 'Export 권한이 없습니다' : 
                 r.status === 500 ? '서버 오류가 발생했습니다' :
                 `Export 요청 실패 (${r.status})`,
        details: errorText || undefined,
      };
      throw error;
    }
    
    return r.json();
  } catch (e: any) {
    if (e instanceof TypeError || e.message?.includes('fetch')) {
      const error: ApiError = {
        kind: 'network',
        message: '서버에 연결할 수 없습니다',
        details: e.message,
      };
      throw error;
    }
    throw e;
  }
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
  if (isMock(cfg)) {
    console.log('[MOCK] postReconCreate:', body);
    await new Promise(resolve => setTimeout(resolve, 200));
    return { sessionId: 'recon-mock-1', status: 'open' };
  }

  try {
    const r = await fetch(`${cfg.baseUrl}/v1/accounting/reconciliation/sessions`, {
      method: 'POST',
      headers: mkHeaders(cfg, { 'Idempotency-Key': opts?.idem ?? await mkUUID() }),
      body: JSON.stringify(body),
    });
    
    if (!r.ok) {
      const errorText = await r.text().catch(() => '');
      const error: ApiError = {
        kind: r.status >= 400 && r.status < 500 ? 'client' : 'server',
        status: r.status,
        message: r.status === 403 ? '대사 권한이 없습니다' : 
                 r.status === 500 ? '서버 오류가 발생했습니다' :
                 `대사 세션 생성 실패 (${r.status})`,
        details: errorText || undefined,
      };
      throw error;
    }
    
    return r.json();
  } catch (e: any) {
    if (e instanceof TypeError || e.message?.includes('fetch')) {
      const error: ApiError = {
        kind: 'network',
        message: '서버에 연결할 수 없습니다',
        details: e.message,
      };
      throw error;
    }
    throw e;
  }
}

/**
 * 수동 매칭 적용
 */
export async function postReconMatch(cfg: ClientCfg, sessionId: string, bank_id: string, ledger_id: string, opts?: IdemOpts) {
  if (isMock(cfg)) {
    console.log('[MOCK] postReconMatch:', { sessionId, bank_id, ledger_id });
    await new Promise(resolve => setTimeout(resolve, 200));
    return { ok: true };
  }

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

