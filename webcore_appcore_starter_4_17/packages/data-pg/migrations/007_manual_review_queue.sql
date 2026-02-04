-- Manual Review Queue 테이블
-- R7-H+1: 수동 검토 워크플로우를 위한 큐 관리

CREATE TABLE IF NOT EXISTS accounting_manual_review_queue (
  id              bigserial      PRIMARY KEY,
  tenant          text           NOT NULL,
  posting_id      text           NOT NULL,
  risk_level      text           NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
  reasons         jsonb          NOT NULL DEFAULT '[]'::jsonb,
  source          text           NOT NULL,  -- "HUD", "BFF", "IMPORT", ...
  status          text           NOT NULL CHECK (status IN ('PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED')),
  assignee        text           NULL,      -- 담당자 ID (X-User-Id)
  note            text           NULL,      -- 검토 코멘트
  created_at      timestamptz    NOT NULL DEFAULT now(),
  updated_at      timestamptz    NOT NULL DEFAULT now()
);

-- 인덱스: 테넌트별 상태별 조회용
CREATE INDEX IF NOT EXISTS idx_manual_review_tenant_status
  ON accounting_manual_review_queue (tenant, status, created_at DESC);

-- 인덱스: Posting ID 조회용
CREATE INDEX IF NOT EXISTS idx_manual_review_posting
  ON accounting_manual_review_queue (tenant, posting_id);

-- 인덱스: 담당자별 조회용
CREATE INDEX IF NOT EXISTS idx_manual_review_assignee
  ON accounting_manual_review_queue (tenant, assignee, status);

