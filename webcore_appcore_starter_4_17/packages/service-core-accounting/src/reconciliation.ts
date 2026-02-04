/**
 * 대사(Reconciliation) 세션/매칭 로직
 * 
 * @module service-core-accounting/reconciliation
 */

import crypto from 'node:crypto';
import { PgReconRepo, type ReconSessionRow } from '@appcore/data-pg';
import { parseAmount } from './rules.js';

const usePg = process.env.USE_PG === '1';
const pgRecon = usePg ? new PgReconRepo() : null;
const pgEnabled = () => usePg && pgRecon;

export type BankTxn = {
  id: string;
  date: string;
  amount: string;
  currency: string;
  desc?: string;
  description?: string;
};

export type LedgerEntry = {
  id: string;
  date: string;
  amount: string;
  currency: string;
  account: string;
  memo?: string;
};

export type ReconPayload = {
  bank: BankTxn[];
  ledger: LedgerEntry[];
  tolerance?: { days?: number };
  client_request_id?: string;
};

export type ReconMatch = {
  bank_id: string;
  ledger_id: string;
  confidence: number;
  rule: string;
};

export type ReconSession = {
  sessionId: string;
  tenant: string;
  created_at: string;
  matches: ReconMatch[];
  unmatched_bank: string[];
  unmatched_ledger: string[];
};

const sessions = new Map<string, ReconSession>();
const idemCache = new Map<string, string>(); // tenant:idem → sessionId

function dayDiff(a: string, b: string): number {
  return Math.abs(Math.floor((Date.parse(a) - Date.parse(b)) / 86400000));
}

function score(tx: BankTxn, le: LedgerEntry, tolDays: number): { s: number; rule: string } {
  if (tx.currency !== le.currency) {
    return { s: 0, rule: 'currency_mismatch' };
  }
  
  const a = parseAmount(tx.amount);
  const b = parseAmount(le.amount);
  if (a !== b) {
    return { s: 0, rule: 'amount_mismatch' };
  }
  
  const d = dayDiff(tx.date, le.date);
  if (d === 0) {
    return { s: 1.0, rule: 'exact_amount_date' };
  }
  if (d <= Math.max(1, tolDays)) {
    return { s: 0.8, rule: 'amount_date_within_tol' };
  }
  
  // 아주 약한 후보 (설명 토큰 힌트)
  const td = (tx.desc ?? tx.description ?? '').toLowerCase();
  const lm = (le.memo ?? '').toLowerCase();
  if (td && lm && (td.includes('fee') && lm.includes('fee'))) {
    return { s: 0.5, rule: 'token_hint_fee' };
  }
  
  return { s: 0, rule: 'date_far' };
}

/**
 * 대사 세션 생성
 * 
 * @param tenant - 테넌트 ID
 * @param payload - 대사 페이로드 (bank/ledger 트랜잭션)
 * @param opts - 옵션 (멱등성 키 등)
 * @returns 대사 세션
 */
export async function createReconSession(
  tenant: string,
  payload: ReconPayload,
  opts?: { idem?: string }
): Promise<ReconSession> {
  const tol = payload.tolerance?.days ?? 3;
  const idemKey = opts?.idem ? `${tenant}:${opts.idem}` : undefined;
  
  // 멱등성 캐시 확인
  if (idemKey && idemCache.has(idemKey)) {
    const sid = idemCache.get(idemKey)!;
    return sessions.get(sid)!;
  }
  
  const bank = payload.bank ?? [];
  const ledger = payload.ledger ?? [];
  const usedLedger = new Set<string>();
  const matches: ReconMatch[] = [];
  
  // 탐욕 매칭: 각 bank 트랜잭션에 대해 최고 점수 ledger 엔트리 매칭
  for (const tx of bank) {
    let best: { s: number; le?: LedgerEntry; rule: string } = { s: 0, rule: 'none' };
    
    for (const le of ledger) {
      if (usedLedger.has(le.id)) continue;
      const { s, rule } = score(tx, le, tol);
      if (s > best.s) {
        best = { s, le, rule };
      }
    }
    
    if (best.le && best.s >= 0.8) {
      usedLedger.add(best.le.id);
      matches.push({
        bank_id: tx.id,
        ledger_id: best.le.id,
        confidence: best.s,
        rule: best.rule,
      });
    }
  }
  
  const unmatched_bank = bank
    .filter(tx => !matches.find(m => m.bank_id === tx.id))
    .map(tx => tx.id);
  const unmatched_ledger = ledger
    .filter(le => !matches.find(m => m.ledger_id === le.id))
    .map(le => le.id);
  
  const sessionId = `rc_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
  const session: ReconSession = {
    sessionId,
    tenant,
    created_at: new Date().toISOString(),
    matches,
    unmatched_bank,
    unmatched_ledger,
  };
  
  if (pgEnabled()) {
    const row: ReconSessionRow = {
      session_id: sessionId,
      tenant,
      created_at: session.created_at,
      matches,
      unmatched_bank,
      unmatched_ledger,
      idem_key: opts?.idem ?? null,
    };
    await pgRecon!.insert(row);
  } else {
    sessions.set(sessionId, session);
    if (idemKey) {
      idemCache.set(idemKey, sessionId);
    }
  }
  
  return session;
}

/**
 * 대사 세션 조회
 * 
 * @param sessionId - 세션 ID
 * @returns 대사 세션 또는 null
 */
export async function getReconSession(sessionId: string): Promise<ReconSession | null> {
  if (pgEnabled()) {
    const r = await pgRecon!.get(sessionId);
    if (!r) {
      return null;
    }
    return {
      sessionId: r.session_id,
      tenant: r.tenant,
      created_at: r.created_at,
      matches: r.matches,
      unmatched_bank: r.unmatched_bank,
      unmatched_ledger: r.unmatched_ledger,
    };
  }
  return sessions.get(sessionId) ?? null;
}

/**
 * 수동 매칭 적용
 * 
 * @param sessionId - 세션 ID
 * @param bank_id - 은행 트랜잭션 ID
 * @param ledger_id - 원장 엔트리 ID
 * @returns 업데이트된 대사 세션 또는 null
 */
export async function applyReconMatch(
  sessionId: string,
  bank_id: string,
  ledger_id: string
): Promise<ReconSession | null> {
  const s = await getReconSession(sessionId);
  if (!s) {
    return null;
  }
  
  if (!s.matches.find(m => m.bank_id === bank_id && m.ledger_id === ledger_id)) {
    s.matches.push({
      bank_id,
      ledger_id,
      confidence: 0.7,
      rule: 'manual',
    });
  }
  
  s.unmatched_bank = s.unmatched_bank.filter(x => x !== bank_id);
  s.unmatched_ledger = s.unmatched_ledger.filter(x => x !== ledger_id);
  
  if (pgEnabled()) {
    await pgRecon!.upsertMatch(sessionId, s.matches, s.unmatched_bank, s.unmatched_ledger);
  } else {
    sessions.set(sessionId, s);
  }
  
  return s;
}

