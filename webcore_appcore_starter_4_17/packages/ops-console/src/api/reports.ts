/**
 * Collector Reports API 래퍼
 * 
 * @module reports
 */

import { get, post } from './client';

export interface ReportSummary {
  id: string;
  createdAt: number;
  updatedAt: number;
  severity?: 'info' | 'warn' | 'block';
  policyVersion?: string;
}

export interface ReportsResponse {
  reports: ReportSummary[];
  pagination: {
    page: number;
    limit: number;
    totalCount: number;
    totalPages: number;
  };
}

export interface GetReportsParams {
  severity?: 'info' | 'warn' | 'block';
  policy_version?: string;
  since?: number;
  page?: number;
  limit?: number;
}

export interface Report {
  id: string;
  tenantId: string;
  report: unknown;
  markdown?: string;
  createdAt: number;
  updatedAt: number;
}

export interface SignResponse {
  token: string;
  expiresAt: number;
  issuedAt: number;
  bundleUrl: string;
}

export interface SignHistoryEntry {
  requestedBy: string;
  issuedAt: number;
  expiresAt: number;
  createdAt: number;
  tokenPreview: string;
}

export interface SignHistory {
  reportId: string;
  history: SignHistoryEntry[];
  count: number;
}

export interface BundleFile {
  name: string;
  size: number;
  checksum: string;
}

export interface BundleMeta {
  reportId: string;
  files: BundleFile[];
  totalFiles: number;
  totalSize: number;
  estimatedZipSize: number;
  checksums: Record<string, string>;
  createdAt: number;
  updatedAt: number;
}

export interface TimelineBucket {
  time: number;
  info: number;
  warn: number;
  block: number;
}

export interface Timeline {
  window_h: number;
  buckets: TimelineBucket[];
}

/**
 * 리포트 목록 조회 (서버 측 필터링)
 */
export async function getReports(params?: GetReportsParams): Promise<ReportsResponse> {
  const queryParams = new URLSearchParams();
  
  if (params?.severity) {
    queryParams.append('severity', params.severity);
  }
  if (params?.policy_version) {
    queryParams.append('policy_version', params.policy_version);
  }
  if (params?.since) {
    queryParams.append('since', params.since.toString());
  }
  if (params?.page) {
    queryParams.append('page', params.page.toString());
  }
  if (params?.limit) {
    queryParams.append('limit', params.limit.toString());
  }
  
  const queryString = queryParams.toString();
  const url = queryString ? `/reports?${queryString}` : '/reports';
  
  return get<ReportsResponse>(url);
}

/**
 * 리포트 상세 조회
 */
export async function getReport(id: string): Promise<Report> {
  return get<Report>(`/reports/${id}`);
}

/**
 * 리포트 서명 요청
 */
export async function signReport(id: string): Promise<SignResponse> {
  return post<SignResponse>(`/reports/${id}/sign`, {});
}

/**
 * 타임라인 조회
 */
export async function getTimeline(windowH: number = 24): Promise<Timeline> {
  return get<Timeline>(`/timeline?window_h=${windowH}`);
}

/**
 * 서명 이력 조회
 */
export async function getSignHistory(id: string): Promise<SignHistory> {
  return get<SignHistory>(`/reports/${id}/sign-history`);
}

/**
 * 번들 메타 정보 조회
 */
export async function getBundleMeta(id: string): Promise<BundleMeta> {
  return get<BundleMeta>(`/reports/${id}/bundle-meta`);
}

/**
 * 번들 다운로드 URL 생성
 */
export function getBundleDownloadUrl(id: string, token: string): string {
  const baseUrl = import.meta.env.VITE_COLLECTOR_URL || 'http://localhost:9090';
  return `${baseUrl}/reports/${id}/bundle.zip?token=${token}`;
}

