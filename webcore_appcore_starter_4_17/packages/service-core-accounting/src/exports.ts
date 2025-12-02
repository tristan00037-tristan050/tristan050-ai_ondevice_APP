/**
 * Export 잡 관리
 * 
 * @module service-core-accounting/exports
 */

import crypto from 'node:crypto';
import { PgExportRepo } from '@appcore/data-pg/repos/exportsRepo.js';
import type { ExportJobRow } from '@appcore/data-pg';

export type ExportFilters = {
  since?: string;
  until?: string;
  severity?: string[];
  limitDays?: number;
  policy_version?: string;
};

export type ExportStatus = 'pending' | 'running' | 'done' | 'failed' | 'expired';

export interface ExportJob {
  jobId: string;
  tenant: string;
  status: ExportStatus;
  created_at: string;
  filters: ExportFilters;
  exp?: string;
  downloadUrl?: string;
  file_count?: number;
  total_bytes?: number;
  sha256?: string;
  manifest?: any;
  error?: string;
}

const memJobs = new Map<string, ExportJob>();
const memIdem = new Map<string, string>(); // tenant:idem → jobId
const usePg = process.env.USE_PG === '1';
const pgRepo = usePg ? new PgExportRepo() : null;

function secret(): string {
  return process.env.EXPORT_SIGN_SECRET ?? 'dev-export-secret';
}

function hmac(secret: string, msg: string) {
  return crypto.createHmac('sha256', secret).update(msg).digest('hex');
}

export function signExport(manifest: string, expiresAtIso: string) {
  const cur = process.env.EXPORT_SIGN_SECRET ?? '';
  if (!cur) throw Object.assign(new Error('missing_export_sign_secret'), { status: 500 });
  const base = `${manifest}|${expiresAtIso}`;
  return hmac(cur, base);
}

export function verifyExportSignature(manifest: string, expiresAtIso: string, sig: string) {
  const cur = process.env.EXPORT_SIGN_SECRET ?? '';
  const prev = process.env.EXPORT_SIGN_SECRET_PREV ?? '';
  const base = `${manifest}|${expiresAtIso}`;
  const okCur = cur ? hmac(cur, base) === sig : false;
  const okPrev = prev ? hmac(prev, base) === sig : false;
  return okCur || okPrev;
}

function sign(jobId: string, exp: string): string {
  // 기존 호환성 유지 (manifest 형식으로 변환)
  const manifest = JSON.stringify({ jobId });
  return signExport(manifest, exp);
}

/**
 * Export 잡 생성
 * 
 * @param tenant - 테넌트 ID
 * @param filters - 필터 조건
 * @param opts - 옵션 (멱등성 키 등)
 * @returns Export 잡 정보
 */
export async function createExportJob(
  tenant: string,
  filters: ExportFilters,
  opts?: { idem?: string; ttlSeconds?: number; now?: number }
): Promise<ExportJob> {
  const nowMs = opts?.now ?? Date.now();
  const ttl = opts?.ttlSeconds ?? 7 * 24 * 60 * 60; // 7일 기본
  const exp = new Date(nowMs + ttl * 1000).toISOString();
  const jobId = `job_${nowMs}_${Math.random().toString(36).slice(2, 8)}`;
  
  // 데모 단계: 즉시 완료 처리(운영 구현 시 비동기 파이프라인으로 대체)
  const s = sign(jobId, exp);
  const manifest = {
    file_count: 1,
    total_bytes: 0,
    sha256: crypto.createHash('sha256').update(jobId).digest('hex'),
    created_at: new Date(nowMs).toISOString(),
  };
  
  const job: ExportJob = {
    jobId,
    tenant,
    status: 'done',
    filters,
    created_at: new Date(nowMs).toISOString(),
    exp,
    downloadUrl: `/v1/accounting/exports/download/${jobId}?exp=${encodeURIComponent(exp)}&sig=${s}`,
    file_count: 1,
    total_bytes: 0,
    sha256: manifest.sha256,
  };
  
  if (usePg && pgRepo) {
    // 멱등 처리
    if (opts?.idem) {
      const existing = await pgRepo.getByIdem(tenant, opts.idem);
      if (existing) {
      return {
        jobId: existing.job_id,
        tenant: existing.tenant,
        status: existing.status as ExportStatus,
        created_at: existing.created_at,
        filters: existing.filters,
        exp: new Date(Number(existing.exp) * 1000).toISOString(),
        sha256: existing.sha256,
        manifest: existing.manifest as any,
      };
      }
    }
    
    const row: ExportJobRow = {
      job_id: job.jobId,
      tenant: job.tenant,
      status: job.status,
      created_at: job.created_at,
      exp: Math.floor(Date.parse(exp) / 1000),
      sha256: job.sha256!,
      manifest,
      filters,
      idem_key: opts?.idem ?? null,
    };
    await pgRepo.insert(row);
  } else {
    memJobs.set(jobId, job);
    if (opts?.idem) {
      memIdem.set(`${tenant}:${opts.idem}`, jobId);
    }
  }
  
  return job;
}

/**
 * Export 잡 상태 조회
 * 
 * @param jobId - 잡 ID
 * @returns Export 잡 정보
 */
export async function getExportJob(jobId: string): Promise<ExportJob | null> {
  if (usePg && pgRepo) {
    const row = await pgRepo.get(jobId);
    if (!row) {
      return null;
    }
      return {
        jobId: row.job_id,
        tenant: row.tenant,
        status: row.status as ExportStatus,
        created_at: row.created_at,
        filters: row.filters,
        exp: new Date(Number(row.exp) * 1000).toISOString(),
        sha256: row.sha256,
        manifest: row.manifest as any,
      };
  }
  return memJobs.get(jobId) ?? null;
}
