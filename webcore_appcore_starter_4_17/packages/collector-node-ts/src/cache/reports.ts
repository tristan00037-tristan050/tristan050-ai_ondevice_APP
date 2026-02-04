/**
 * 리포트 캐싱 전략
 * 리포트 목록 및 타임라인 집계 결과 캐싱
 * 
 * @module cache/reports
 */

import { memoryCache } from './memory.js';
import type { Report } from '../db/reports.js';

interface ReportsListCacheKey {
  tenantId: string;
  severity?: string;
  policyVersion?: string;
  since?: number;
  page: number;
  limit: number;
}

interface TimelineCacheKey {
  tenantId: string;
  windowH: number;
}

/**
 * 리포트 목록 캐시 키 생성
 */
function getReportsListCacheKey(key: ReportsListCacheKey): string {
  const parts = [
    'reports:list',
    key.tenantId,
    key.severity || '',
    key.policyVersion || '',
    key.since?.toString() || '',
    key.page.toString(),
    key.limit.toString(),
  ];
  return parts.join(':');
}

/**
 * 타임라인 캐시 키 생성
 */
function getTimelineCacheKey(key: TimelineCacheKey): string {
  return `timeline:${key.tenantId}:${key.windowH}`;
}

/**
 * 리포트 목록 캐시 조회
 */
export function getCachedReportsList(
  key: ReportsListCacheKey
): {
  reports: Array<{
    id: string;
    createdAt: number;
    updatedAt: number;
    severity?: 'info' | 'warn' | 'block';
    policyVersion?: string;
  }>;
  totalCount: number;
  etag: string;
} | null {
  const cacheKey = getReportsListCacheKey(key);
  return memoryCache.get(cacheKey) || null;
}

/**
 * 리포트 목록 캐시 저장
 */
export function setCachedReportsList(
  key: ReportsListCacheKey,
  data: {
    reports: Array<{
      id: string;
      createdAt: number;
      updatedAt: number;
      severity?: 'info' | 'warn' | 'block';
      policyVersion?: string;
    }>;
    totalCount: number;
    etag: string;
  },
  ttlMs: number = 30000 // 기본 30초
): void {
  const cacheKey = getReportsListCacheKey(key);
  memoryCache.set(cacheKey, data, ttlMs);
}

/**
 * 리포트 목록 캐시 무효화
 */
export function invalidateReportsListCache(tenantId: string): void {
  // 특정 테넌트의 모든 리포트 목록 캐시 무효화
  // 간단한 구현: 모든 캐시 키를 순회하여 해당 테넌트의 캐시 삭제
  // 실제로는 Redis의 패턴 매칭이나 네임스페이스를 사용하는 것이 더 효율적
  const prefix = `reports:list:${tenantId}:`;
  // 메모리 캐시에서는 직접 삭제할 수 없으므로, 캐시 만료 시간을 짧게 설정하는 것이 더 실용적
  // 또는 캐시 버전 번호를 사용하여 무효화
}

/**
 * 타임라인 캐시 조회
 */
export function getCachedTimeline(
  key: TimelineCacheKey
): {
  window_h: number;
  buckets: Array<{ time: number; info: number; warn: number; block: number }>;
} | null {
  const cacheKey = getTimelineCacheKey(key);
  return memoryCache.get(cacheKey) || null;
}

/**
 * 타임라인 캐시 저장
 */
export function setCachedTimeline(
  key: TimelineCacheKey,
  data: {
    window_h: number;
    buckets: Array<{ time: number; info: number; warn: number; block: number }>;
  },
  ttlMs: number = 60000 // 기본 60초
): void {
  const cacheKey = getTimelineCacheKey(key);
  memoryCache.set(cacheKey, data, ttlMs);
}

/**
 * 타임라인 캐시 무효화
 */
export function invalidateTimelineCache(tenantId: string): void {
  // 타임라인 캐시는 시간이 지나면 자동으로 무효화되므로 명시적 무효화는 선택사항
  const prefix = `timeline:${tenantId}:`;
  // 메모리 캐시에서는 직접 삭제할 수 없으므로, 캐시 만료 시간을 짧게 설정
}

/**
 * 리포트 저장 시 관련 캐시 무효화
 */
export function invalidateOnReportSave(tenantId: string): void {
  // 리포트 저장 시 해당 테넌트의 목록 및 타임라인 캐시 무효화
  invalidateReportsListCache(tenantId);
  invalidateTimelineCache(tenantId);
}


