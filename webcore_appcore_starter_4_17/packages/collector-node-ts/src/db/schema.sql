-- Collector 데이터베이스 스키마
-- PostgreSQL 기반

-- 리포트 테이블
CREATE TABLE IF NOT EXISTS reports (
  id VARCHAR(255) PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL,
  report_data JSONB NOT NULL,
  markdown TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

-- 인덱스 생성 (쿼리 최적화)
CREATE INDEX IF NOT EXISTS idx_reports_tenant_id ON reports(tenant_id);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_tenant_created ON reports(tenant_id, created_at DESC);

-- JSONB 인덱스 (severity, policy_version 필터링 최적화)
CREATE INDEX IF NOT EXISTS idx_reports_policy_severity ON reports USING GIN ((report_data->'policy'->'evaluations'));
CREATE INDEX IF NOT EXISTS idx_reports_policy_version ON reports USING GIN ((report_data->'policy'->'policy_version'));

-- 서명 이력 테이블
CREATE TABLE IF NOT EXISTS sign_history (
  id SERIAL PRIMARY KEY,
  report_id VARCHAR(255) NOT NULL,
  tenant_id VARCHAR(255) NOT NULL,
  requested_by VARCHAR(255) NOT NULL,
  token TEXT NOT NULL,
  issued_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL,
  FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_sign_history_report_id ON sign_history(report_id);
CREATE INDEX IF NOT EXISTS idx_sign_history_tenant_id ON sign_history(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sign_history_created_at ON sign_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sign_history_report_tenant ON sign_history(report_id, tenant_id);

-- 서명 토큰 캐시 테이블 (멱등성 보장)
CREATE TABLE IF NOT EXISTS sign_token_cache (
  cache_key VARCHAR(255) PRIMARY KEY,
  token TEXT NOT NULL,
  expires_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL
);

-- 만료된 토큰 정리용 인덱스
CREATE INDEX IF NOT EXISTS idx_sign_token_cache_expires_at ON sign_token_cache(expires_at);

-- 테넌트 격리를 위한 뷰 (선택사항)
CREATE OR REPLACE VIEW reports_summary AS
SELECT 
  id,
  tenant_id,
  created_at,
  updated_at,
  (report_data->'policy'->'evaluations')::jsonb as evaluations,
  report_data->'policy'->>'policy_version' as policy_version
FROM reports;

