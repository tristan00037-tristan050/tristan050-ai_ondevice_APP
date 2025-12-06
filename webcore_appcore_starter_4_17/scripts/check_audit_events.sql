-- ============================================
-- Audit 이벤트 확인 쿼리
-- ============================================
-- 사용법:
--   psql $DATABASE_URL -f scripts/check_audit_events.sql
--   또는
--   psql $DATABASE_URL -c "SELECT ..." (개별 쿼리 실행)
-- ============================================

-- 1. 승인 이벤트 샘플 (approval_apply)
-- top1_selected, selected_rank, ai_score 필드 확인
SELECT 
  action, 
  subject_type, 
  subject_id,
  payload->>'top1_selected' AS top1_selected,
  payload->>'selected_rank' AS selected_rank,
  payload->>'ai_score' AS ai_score,
  payload->>'note' AS note,
  ts
FROM accounting_audit_events
WHERE action = 'approval_apply'
ORDER BY ts DESC
LIMIT 10;

-- 2. Manual Review 이벤트 샘플 (manual_review_request)
-- reason_code, amount, currency, is_high_value 필드 확인
SELECT 
  action, 
  subject_type, 
  subject_id,
  payload->>'reason_code' AS reason_code,
  payload->>'amount' AS amount,
  payload->>'currency' AS currency,
  payload->>'is_high_value' AS is_high_value,
  payload->>'reason' AS reason,
  ts
FROM accounting_audit_events
WHERE action = 'manual_review_request'
ORDER BY ts DESC
LIMIT 10;

-- 3. External Sync 이벤트 샘플
-- external_sync_start, external_sync_success, external_sync_error 확인
SELECT 
  action,
  subject_id AS source,
  payload->>'source' AS source_from_payload,
  payload->>'items' AS items,
  payload->>'pages' AS pages,
  payload->>'error' AS error,
  payload->>'since' AS since,
  ts
FROM accounting_audit_events
WHERE action IN ('external_sync_start', 'external_sync_success', 'external_sync_error')
ORDER BY ts DESC
LIMIT 20;

-- 4. 전체 이벤트 요약 (최근 1시간)
SELECT 
  action,
  COUNT(*) AS count,
  MIN(ts) AS first_event,
  MAX(ts) AS last_event
FROM accounting_audit_events
WHERE ts >= NOW() - INTERVAL '1 hour'
GROUP BY action
ORDER BY count DESC;

-- 5. 승인 이벤트 상세 분석 (payload 필드 존재 여부 확인)
SELECT 
  COUNT(*) AS total,
  COUNT(payload->>'top1_selected') AS has_top1_selected,
  COUNT(payload->>'top1_selected') AS has_top1_selected_alt,  -- 오타 대비
  COUNT(payload->>'selected_rank') AS has_selected_rank,
  COUNT(payload->>'ai_score') AS has_ai_score
FROM accounting_audit_events
WHERE action = 'approval_apply'
  AND ts >= NOW() - INTERVAL '24 hours';

-- 6. Manual Review 이벤트 상세 분석 (payload 필드 존재 여부 확인)
SELECT 
  COUNT(*) AS total,
  COUNT(payload->>'reason_code') AS has_reason_code,
  COUNT(payload->>'amount') AS has_amount,
  COUNT(payload->>'currency') AS has_currency,
  COUNT(payload->>'is_high_value') AS has_is_high_value
FROM accounting_audit_events
WHERE action = 'manual_review_request'
  AND ts >= NOW() - INTERVAL '24 hours';

-- 7. External Sync 이벤트 통계 (최근 24시간)
SELECT 
  action,
  payload->>'source' AS source,
  COUNT(*) AS count,
  COUNT(*) FILTER (WHERE action = 'external_sync_error') AS error_count
FROM accounting_audit_events
WHERE action IN ('external_sync_start', 'external_sync_success', 'external_sync_error')
  AND ts >= NOW() - INTERVAL '24 hours'
GROUP BY action, payload->>'source'
ORDER BY source, action;

