/**
 * 오프라인 큐: 실패/오프라인 시 암호화 저장 → 온라인 전환 시 재시도
 * 
 * @module app-expo/ui/offline/offline-queue
 */

import NetInfo from '@react-native-community/netinfo';
import { getSecureKV } from '../../security/secure-storage.js';
import { mkHeaders, type ClientCfg } from '../../hud/accounting-api.js';

type QueueItem =
  | { kind: 'approval'; id: string; action: 'approve' | 'reject'; note?: string; idem: string; top1_selected?: boolean; selected_rank?: number; ai_score?: number }
  | { kind: 'export'; body: any; idem: string }
  | { kind: 'recon_create'; body: any; idem: string }
  | { kind: 'recon_match'; sessionId: string; bank_id: string; ledger_id: string; idem: string }
  | { kind: 'suggest'; body: any; idem: string };

const QUEUE_PREFIX = 'q:acct:';

const kvKey = (n: string) => `${QUEUE_PREFIX}${n}`;

export async function enqueue(item: QueueItem) {
  const kv = await getSecureKV();
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
  const keys = await listQueue();
  for (const k of keys) {
    const kv = await getSecureKV();
    const raw = kv.getString(k);
    if (!raw) {
      continue;
    }
    const item: QueueItem = JSON.parse(raw);
    try {
      await trySend(cfg, item);
      await clearItem(k);
    } catch {
      // 실패 시 item 유지 (다음 flush에서 재시도)
    }
  }
}

let started = false;

export function startQueueAutoFlush(cfg: ClientCfg) {
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


