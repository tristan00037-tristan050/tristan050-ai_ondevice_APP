-- Risk Scores 테이블
-- R8-S1: 고액 거래 리스크 필터링을 위한 리스크 점수 저장

CREATE TABLE IF NOT EXISTS accounting_risk_scores (
  posting_id   text        NOT NULL,
  tenant       text        NOT NULL,
  level        text        NOT NULL CHECK (level IN ('LOW', 'MEDIUM', 'HIGH')),
  score        numeric(5,2) NOT NULL CHECK (score >= 0 AND score <= 100),
  reasons      jsonb       NOT NULL DEFAULT '[]'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant, posting_id)
);

-- 인덱스: 고위험 거래 조회용
CREATE INDEX IF NOT EXISTS idx_risk_scores_high ON accounting_risk_scores (tenant, created_at DESC) 
  WHERE level = 'HIGH';

-- 인덱스: 테넌트별 최근 리스크 조회용
CREATE INDEX IF NOT EXISTS idx_risk_scores_tenant_created ON accounting_risk_scores (tenant, created_at DESC);

