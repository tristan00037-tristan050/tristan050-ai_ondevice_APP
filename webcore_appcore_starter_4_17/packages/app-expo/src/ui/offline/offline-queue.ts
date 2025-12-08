/**
 * 오프라인 큐: 실패/오프라인 시 암호화 저장 → 온라인 전환 시 재시도
 * 
 * @module app-expo/ui/offline/offline-queue
 */

import NetInfo from '@react-native-community/netinfo';
import { getSecureKV } from '../../security/secure-storage';
import { mkHeaders, isMock, type ClientCfg } from '../../hud/accounting-api';

type QueueItem =
  | { kind: 'approval'; id: string; action: 'approve' | 'reject'; note?: string; idem: string; top1_selected?: boolean; selected_rank?: number; ai_score?: number }
  | { kind: 'export'; body: any; idem: string }
  | { kind: 'recon_create'; body: any; idem: string }
  | { kind: 'recon_match'; sessionId: string; bank_id: string; ledger_id: string; idem: string }
  | { kind: 'suggest'; body: any; idem: string };

const QUEUE_PREFIX = 'q:acct:';
const MAX_QUEUE_SIZE = 100; // 최대 큐 길이 상한
const QUEUE_EXPIRY_MS = 24 * 60 * 60 * 1000; // 24시간

const kvKey = (n: string) => `${QUEUE_PREFIX}${n}`;

export async function enqueue(item: QueueItem): Promise<string> {
  // Mock 모드에서는 큐에 넣지 않음
  // (이미 trySend에서 처리하지만, 이중 체크)
  
  const kv = await getSecureKV();
  
  // 현재 큐 크기 확인
  const keys = await listQueue();
  if (keys.length >= MAX_QUEUE_SIZE) {
    throw new Error('QUEUE_FULL');
  }
  
  // 오래된 항목 정리 (24시간 이상)
  const now = Date.now();
  for (const key of keys) {
    try {
      const timestamp = parseInt(key.split('_')[1] || '0');
      if (now - timestamp > QUEUE_EXPIRY_MS) {
        await clearItem(key);
      }
    } catch {
      // 파싱 실패 시 무시
    }
  }
  
  const id = `it_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  kv.set(kvKey(id), JSON.stringify(item));
  return id;
}

export async function listQueue(): Promise<string[]> {
  const kv = await getSecureKV();
  return kv.getAllKeys().filter((k: string) => k.startsWith(QUEUE_PREFIX));
}

export async function clearItem(storageKey: string) {
  const kv = await getSecureKV();
  kv.delete(storageKey);
}

async function trySend(cfg: ClientCfg, item: QueueItem) {
  // Mock 모드에서는 실제 요청을 보내지 않음
  if (isMock(cfg)) {
    console.log('[MOCK] offline-queue trySend:', item.kind);
    // 그냥 성공 처리
    return { success: true, mock: true };
  }
  
  const base = cfg.baseUrl;
  const h = (extra?: Record<string, string>) => mkHeaders(cfg, extra);
  const hdr = (idem: string) => h({ 'Idempotency-Key': idem });

  if (item.kind === 'approval') {
    const body: any = { 
      action: item.action, 
      client_request_id: item.idem, 
      note: item.note 
    };
    
    // 선택 정보 추가 (approve 액션일 때만)
    if (item.action === 'approve') {
      if (item.top1_selected !== undefined) {
        body.top1_selected = item.top1_selected;
      }
      if (item.selected_rank !== undefined) {
        body.selected_rank = item.selected_rank;
      }
      if (item.ai_score !== undefined) {
        body.ai_score = item.ai_score;
      }
    }
    
    const r = await fetch(`${base}/v1/accounting/approvals/${item.id}`, {
      method: 'POST',
      headers: hdr(item.idem),
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      throw new Error(`approval ${r.status}`);
    }
    return await r.json();
  }

  if (item.kind === 'export') {
    const r = await fetch(`${base}/v1/accounting/exports/reports`, {
      method: 'POST',
      headers: hdr(item.idem),
      body: JSON.stringify(item.body),
    });
    if (!r.ok) {
      throw new Error(`export ${r.status}`);
    }
    return await r.json();
  }

  if (item.kind === 'recon_create') {
    const r = await fetch(`${base}/v1/accounting/reconciliation/sessions`, {
      method: 'POST',
      headers: hdr(item.idem),
      body: JSON.stringify(item.body),
    });
    if (!r.ok) {
      throw new Error(`recon create ${r.status}`);
    }
    return await r.json();
  }

  if (item.kind === 'recon_match') {
    const r = await fetch(`${base}/v1/accounting/reconciliation/sessions/${item.sessionId}/match`, {
      method: 'POST',
      headers: hdr(item.idem),
      body: JSON.stringify({ bank_id: item.bank_id, ledger_id: item.ledger_id }),
    });
    if (!r.ok) {
      throw new Error(`recon match ${r.status}`);
    }
    return await r.json();
  }

  if (item.kind === 'suggest') {
    const r = await fetch(`${base}/v1/accounting/postings/suggest`, {
      method: 'POST',
      headers: hdr(item.idem),
      body: JSON.stringify(item.body),
    });
    if (!r.ok) {
      throw new Error(`suggest ${r.status}`);
    }
    return await r.json();
  }
}

export async function flushQueue(cfg: ClientCfg) {
  // Mock 모드에서는 큐를 비우지 않음 (또는 모의로만 처리)
  if (isMock(cfg)) {
    console.log('[MOCK] flushQueue: skip (mock mode)');
    return;
  }
  
  const keys = await listQueue();
  // Rate limit을 고려하여 각 요청 사이에 지연 추가 (429 에러 방지)
  for (let i = 0; i < keys.length; i++) {
    const k = keys[i];
    const kv = await getSecureKV();
    const raw = kv.getString(k);
    if (!raw) {
      continue;
    }
    const item: QueueItem = JSON.parse(raw);
    try {
      await trySend(cfg, item);
      await clearItem(k);
      // Rate limit 방지를 위해 요청 사이에 100ms 지연 (429 에러 방지)
      if (i < keys.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    } catch (err: any) {
      // 실패 시 item 유지 (다음 flush에서 재시도)
      // 429 (Rate Limit) 에러인 경우 더 긴 지연 후 재시도
      if (err?.message?.includes('429')) {
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
    }
  }
}

let started = false;

export function startQueueAutoFlush(cfg: ClientCfg) {
  // Mock 모드에서는 자동 flush를 시작하지 않음
  if (isMock(cfg)) {
    console.log('[MOCK] startQueueAutoFlush: skip (mock mode)');
    return;
  }
  
  if (started) {
    return;
  }
  started = true;
  NetInfo.addEventListener((state) => {
    if (state.isConnected) {
      flushQueue(cfg);
    }
  });
}


