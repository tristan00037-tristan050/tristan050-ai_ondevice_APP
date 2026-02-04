/**
 * CS HUD에서 BFF 호출용 최소 API 래퍼
 * R9-S1: CS 티켓 리스트 조회
 * 
 * @module app-expo/hud/cs-api
 */

import type { ClientCfg } from './accounting-api';
import { bffUrl } from "./bffBase";
import { resolveBffBaseUrl } from "../os/bff";

// accounting-api에서 함수 재사용
import { isMock as _isMock, mkHeaders as _mkHeaders } from './accounting-api';

export interface CsTicket {
  id: number;
  tenant: string;
  subject: string;
  status: 'open' | 'pending' | 'closed';
  createdAt: string; // ISO 문자열
}

export interface ListCsTicketsResponse {
  items: CsTicket[];
}

/**
 * Mock 모드 확인 (accounting-api의 isMock 재사용)
 */
export function isMock(cfg: ClientCfg): boolean {
  return _isMock(cfg);
}

/**
 * CS 티켓 목록 조회
 * 
 * @param cfg - 클라이언트 설정
 * @param params - 조회 파라미터
 * @returns 티켓 목록 응답
 */
export async function fetchCsTickets(
  cfg: ClientCfg,
  params: { status?: string; limit?: number; offset?: number } = {},
): Promise<ListCsTicketsResponse> {
  // Mock 모드: 네트워크 요청 없이 더미 데이터 반환
  if (isMock(cfg)) {
    console.log('[MOCK] fetchCsTickets: returning dummy data');
    return {
      items: [
        {
          id: 1,
          tenant: cfg.tenantId || 'default',
          subject: 'Mock CS Ticket 1',
          status: 'open',
          createdAt: new Date().toISOString(),
        },
        {
          id: 2,
          tenant: cfg.tenantId || 'default',
          subject: 'Mock CS Ticket 2',
          status: 'pending',
          createdAt: new Date(Date.now() - 86400000).toISOString(),
        },
      ],
    };
  }

  // Live 모드: 실제 BFF API 호출
  const { status, limit = 20, offset = 0 } = params;
  const queryParams = new URLSearchParams();
  if (status) queryParams.set('status', status);
  queryParams.set('limit', String(limit));
  queryParams.set('offset', String(offset));

  // OS 공통 resolveBffBaseUrl 사용 (하드코딩 URL 금지)
  const baseUrl =
    (cfg.baseUrl || "").trim().replace(/\/$/, "") ||
    resolveBffBaseUrl().replace(/\/$/, "");
  const url = `${baseUrl}/v1/cs/tickets?${queryParams.toString()}`;
  const headers = _mkHeaders(cfg);

  const response = await fetch(url, {
    method: 'GET',
    headers,
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch CS tickets: ${response.status} ${response.statusText}`);
  }

  const ct = response.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    const text = await response.text();
    throw new Error(
      `CS tickets expected JSON but got "${ct}". baseUrl=${baseUrl}. first200=${text.slice(0, 200)}`
    );
  }
  const data = await response.json();
  return {
    items: Array.isArray(data) ? data : (data.items || []),
  };
}

