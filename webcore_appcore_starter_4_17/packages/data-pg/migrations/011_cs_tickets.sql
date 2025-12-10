/**
 * CS Tickets Table
 * R9-S1: CS 도메인 티켓 테이블 생성
 * 
 * CS 티켓 리스트 및 요약 기능을 위한 최소 스키마
 */

CREATE TABLE IF NOT EXISTS cs_tickets (
  id BIGSERIAL PRIMARY KEY,
  tenant TEXT NOT NULL,
  subject TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'pending', 'closed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 테넌트별, 생성일시 역순 조회를 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_cs_tickets_tenant_created_at 
  ON cs_tickets (tenant, created_at DESC);

-- 상태별 필터링을 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_cs_tickets_tenant_status 
  ON cs_tickets (tenant, status);

