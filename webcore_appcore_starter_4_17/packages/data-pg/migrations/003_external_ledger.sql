-- 외부 원장 트랜잭션 적재 테이블
CREATE TABLE IF NOT EXISTS external_ledger (
  id           BIGSERIAL PRIMARY KEY,
  tenant       TEXT NOT NULL,
  source       TEXT NOT NULL,              -- 'bank-sbx' | 'pg-sbx' | 'erp-sbx' 등
  external_id  TEXT NOT NULL,              -- 외부 트랜잭션 고유 식별자
  ts           TIMESTAMPTZ NOT NULL,       -- 거래 시각
  amount       NUMERIC(18,2) NOT NULL,
  currency     TEXT NOT NULL DEFAULT 'KRW',
  merchant     TEXT,
  account_id   TEXT,
  memo         TEXT,
  raw          JSONB,                      -- 원문 보관
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant, source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_ext_led_tenant_source_ts
  ON external_ledger (tenant, source, ts DESC);
CREATE INDEX IF NOT EXISTS idx_ext_led_tenant_source_amt
  ON external_ledger (tenant, source, amount);

-- 소스별 오프셋/커서 관리
CREATE TABLE IF NOT EXISTS external_ledger_offset (
  id          BIGSERIAL PRIMARY KEY,
  tenant      TEXT NOT NULL,
  source      TEXT NOT NULL,
  last_cursor TEXT,
  last_ts     TIMESTAMPTZ,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant, source)
);

