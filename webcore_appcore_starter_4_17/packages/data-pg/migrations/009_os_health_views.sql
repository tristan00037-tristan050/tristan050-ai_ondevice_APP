-- OS Health & Observability 뷰
-- R7-H+3: 에러율, 성공률, 지연 시간 집계

-- 1) BFF Health 집계 (audit_events 기반)
-- 참고: 실제 access log는 별도 테이블이 필요하지만, 지금은 audit_events의 status code를 활용
CREATE OR REPLACE VIEW accounting_os_bff_health AS
SELECT
  tenant,
  now() - interval '24 hours' AS window_start,
  now() AS window_end,
  COUNT(*) AS bff_total_count,
  COUNT(*) FILTER (WHERE (payload->>'status')::int >= 500) AS bff_5xx_count,
  COUNT(*) FILTER (WHERE (payload->>'status')::int >= 400 AND (payload->>'status')::int < 500) AS bff_4xx_count,
  COUNT(*) FILTER (WHERE (payload->>'status')::int < 400) AS bff_success_count,
  CASE 
    WHEN COUNT(*) > 0 THEN 
      1.0 - (COUNT(*) FILTER (WHERE (payload->>'status')::int >= 400)::numeric / COUNT(*)::numeric)
    ELSE 0.0
  END AS success_rate,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY (payload->>'latency_ms')::numeric) FILTER (WHERE (payload->>'latency_ms') IS NOT NULL) AS p95_latency_ms
FROM accounting_audit_events
WHERE ts >= now() - interval '24 hours'
  AND action IN ('bff_request', 'api_call')  -- 실제로는 access log에서 가져와야 함
GROUP BY tenant;

-- 2) 간단한 Health 집계 (audit_events의 일반적인 패턴 활용)
-- 실제로는 access log 테이블이 필요하지만, 지금은 audit_events 기반으로 추정
CREATE OR REPLACE VIEW accounting_os_health_summary AS
SELECT
  tenant,
  now() - interval '24 hours' AS window_start,
  now() AS window_end,
  -- 전체 요청 수 (approval_apply, export_create 등으로 추정)
  COUNT(*) FILTER (WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')) AS total_requests,
  -- 성공 요청 (에러가 없는 경우)
  COUNT(*) FILTER (
    WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')
    AND (payload->>'error') IS NULL
  ) AS success_requests,
  -- 실패 요청 (payload에 error가 있는 경우)
  COUNT(*) FILTER (
    WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')
    AND (payload->>'error') IS NOT NULL
  ) AS error_requests,
  -- 성공률 계산
  CASE 
    WHEN COUNT(*) FILTER (WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')) > 0 THEN
      1.0 - (
        COUNT(*) FILTER (
          WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')
          AND (payload->>'error') IS NOT NULL
        )::numeric / 
        COUNT(*) FILTER (WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request'))::numeric
      )
    ELSE 1.0
  END AS success_rate,
  -- P95 지연 시간 (payload에 latency_ms가 있는 경우)
  PERCENTILE_CONT(0.95) WITHIN GROUP (
    ORDER BY (payload->>'latency_ms')::numeric
  ) FILTER (
    WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')
    AND (payload->>'latency_ms') IS NOT NULL
  ) AS p95_latency_ms
FROM accounting_audit_events
WHERE ts >= now() - interval '24 hours'
GROUP BY tenant;

