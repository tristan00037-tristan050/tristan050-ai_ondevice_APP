-- OS Dashboard용 집계 뷰
-- R7-H+2: 파일럿 전체 건강 상태를 한 번에 보여주는 집계 뷰

-- 1) 최근 24시간 기준 파일럿 지표
CREATE OR REPLACE VIEW accounting_os_pilot_summary AS
SELECT
  tenant,
  now() - interval '24 hours' AS window_start,
  now() AS window_end,
  COUNT(*) FILTER (WHERE action = 'suggest_call' OR payload->>'action' = 'suggest') AS suggest_calls,
  COUNT(*) FILTER (
    WHERE action = 'approval_apply' 
    AND (payload->>'top1_selected')::boolean = true
  ) AS suggest_top1_ok,
  COUNT(*) FILTER (WHERE action = 'manual_review_request') AS manual_review_requests
FROM accounting_audit_events
WHERE ts >= now() - interval '24 hours'
GROUP BY tenant;

-- 2) Manual Review / Risk 하이라이트
CREATE OR REPLACE VIEW accounting_os_risk_summary AS
SELECT
  tenant,
  COUNT(*) FILTER (WHERE level = 'HIGH') AS high_risk_total,
  COUNT(*) FILTER (WHERE level = 'HIGH' AND created_at >= now() - interval '24 hours') AS high_risk_24h,
  COUNT(*) FILTER (WHERE level = 'MEDIUM' AND created_at >= now() - interval '24 hours') AS medium_risk_24h,
  COUNT(*) FILTER (WHERE level = 'LOW' AND created_at >= now() - interval '24 hours') AS low_risk_24h
FROM accounting_risk_scores
WHERE created_at IS NOT NULL
GROUP BY tenant;

-- 3) Manual Review Queue 요약
CREATE OR REPLACE VIEW accounting_os_manual_review_summary AS
SELECT
  tenant,
  COUNT(*) FILTER (WHERE status = 'PENDING') AS manual_review_pending,
  COUNT(*) FILTER (WHERE status = 'IN_REVIEW') AS manual_review_in_review,
  COUNT(*) FILTER (WHERE status = 'APPROVED' AND updated_at >= now() - interval '24 hours') AS manual_review_approved_24h,
  COUNT(*) FILTER (WHERE status = 'REJECTED' AND updated_at >= now() - interval '24 hours') AS manual_review_rejected_24h
FROM accounting_manual_review_queue
GROUP BY tenant;

