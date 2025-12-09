/**
 * OS Dashboard Engine Summary View
 * R8-S2: 엔진 모드별 집계 뷰
 * 
 * 지난 24시간 기준 테넌트별, engine_mode별 postings_suggest 이벤트 카운트
 */

CREATE OR REPLACE VIEW accounting_os_engine_summary AS
SELECT
  tenant,
  (payload->>'engine_mode')::text AS engine_mode,
  COUNT(*) AS cnt
FROM accounting_audit_events
WHERE
  action = 'postings_suggest'
  AND payload ? 'engine_mode'
  AND ts >= now() - interval '24 hours'
GROUP BY tenant, (payload->>'engine_mode');

-- 인덱스가 이미 있다면 활용 (action, ts, payload)
-- 필요시 추가 인덱스:
-- CREATE INDEX IF NOT EXISTS idx_audit_events_engine_mode 
--   ON accounting_audit_events(tenant, action, ts) 
--   WHERE action = 'postings_suggest' AND payload ? 'engine_mode';

