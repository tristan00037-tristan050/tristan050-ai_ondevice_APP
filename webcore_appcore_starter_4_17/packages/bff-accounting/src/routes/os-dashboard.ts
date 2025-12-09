/**
 * OS Dashboard API 라우트
 * 
 * @module bff-accounting/routes/os-dashboard
 */

import { Router } from 'express';
import { requireTenantAuth, requireRole } from '../shared/guards.js';
import { pool } from '@appcore/data-pg';

const router = Router();

/**
 * GET /v1/accounting/os/dashboard
 * OS Dashboard용 집계 데이터 조회
 */
router.get(
  '/dashboard',
  requireTenantAuth,
  requireRole('operator'),
  async (req: any, res: any, next: any) => {
    try {
      // 쿼리 파라미터 파싱
      const fromParam = req.query.from as string | undefined;
      const toParam = req.query.to as string | undefined;
      const tenantParam = req.query.tenant as string | undefined;
      
      // 테넌트: 쿼리 파라미터 우선, 없으면 헤더, 없으면 기본값
      const tenant = tenantParam || req.ctx?.tenant || req.headers['x-tenant'] as string || 'default';
      
      // 날짜 범위: 쿼리 파라미터 우선, 없으면 기본값 (지난 7일)
      let windowFrom: Date;
      let windowTo: Date;
      
      if (fromParam && toParam) {
        windowFrom = new Date(fromParam);
        windowTo = new Date(toParam);
      } else {
        // 기본값: 지난 7일
        windowTo = new Date();
        windowFrom = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
      }
      
      // 유효성 검사
      if (isNaN(windowFrom.getTime()) || isNaN(windowTo.getTime())) {
        return res.status(400).json({
          error_code: 'INVALID_DATE',
          message: 'Invalid date format. Use YYYY-MM-DD format.',
        });
      }
      
      if (windowFrom > windowTo) {
        return res.status(400).json({
          error_code: 'INVALID_DATE_RANGE',
          message: 'from date must be before to date',
        });
      }
      
      const windowFromISO = windowFrom.toISOString();
      const windowToISO = windowTo.toISOString();
      
      // 1. 파일럿 지표 조회 (동적 날짜 범위)
      const pilotQuery = `
        SELECT 
          COUNT(*) FILTER (WHERE action = 'suggest_call' OR payload->>'action' = 'suggest') AS suggest_calls,
          COUNT(*) FILTER (
            WHERE action = 'approval_apply' 
            AND (payload->>'top1_selected')::boolean = true
          ) AS suggest_top1_ok,
          COUNT(*) FILTER (WHERE action = 'manual_review_request') AS manual_review_requests
        FROM accounting_audit_events
        WHERE tenant = $1 AND ts >= $2 AND ts <= $3
      `;
      const pilotResult = await pool.query(pilotQuery, [tenant, windowFromISO, windowToISO]);
      const pilot = pilotResult.rows[0] || {
        suggest_calls: 0,
        suggest_top1_ok: 0,
        manual_review_requests: 0,
      };
      
      // Top-1 정확도 계산
      const top1Accuracy = pilot.suggest_calls > 0
        ? pilot.suggest_top1_ok / pilot.suggest_calls
        : 0;
      
      // Manual Review 비율 계산
      const manualReviewRate = pilot.suggest_calls > 0
        ? pilot.manual_review_requests / pilot.suggest_calls
        : 0;
      
      // 2. Risk 요약 조회 (동적 날짜 범위)
      const riskQuery = `
        SELECT 
          COUNT(*) FILTER (WHERE level = 'HIGH' AND created_at >= $2 AND created_at <= $3) AS high_risk_count,
          COUNT(*) FILTER (WHERE level = 'MEDIUM' AND created_at >= $2 AND created_at <= $3) AS medium_risk_count,
          COUNT(*) FILTER (WHERE level = 'LOW' AND created_at >= $2 AND created_at <= $3) AS low_risk_count
        FROM accounting_risk_scores
        WHERE tenant = $1 AND created_at IS NOT NULL
      `;
      const riskResult = await pool.query(riskQuery, [tenant, windowFromISO, windowToISO]);
      const risk = riskResult.rows[0] || {
        high_risk_count: 0,
        medium_risk_count: 0,
        low_risk_count: 0,
      };
      
      // 3. Manual Review Queue 요약 조회
      const queueQuery = `
        SELECT 
          manual_review_pending,
          manual_review_in_review,
          manual_review_approved_24h,
          manual_review_rejected_24h
        FROM accounting_os_manual_review_summary
        WHERE tenant = $1
      `;
      const queueResult = await pool.query(queueQuery, [tenant]);
      const queue = queueResult.rows[0] || {
        manual_review_pending: 0,
        manual_review_in_review: 0,
        manual_review_approved_24h: 0,
        manual_review_rejected_24h: 0,
      };
      
      // 4. Health 집계 조회 (최근 5분 기준)
      const health5mFrom = new Date(Date.now() - 5 * 60 * 1000).toISOString();
      const healthQuery = `
        SELECT 
          COUNT(*) FILTER (
            WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')
            AND (payload->>'error') IS NULL
          ) AS success_count,
          COUNT(*) FILTER (
            WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')
            AND (payload->>'error') IS NOT NULL
          ) AS error_count,
          COUNT(*) FILTER (
            WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')
          ) AS total_count,
          PERCENTILE_CONT(0.95) WITHIN GROUP (
            ORDER BY (payload->>'latency_ms')::numeric
          ) FILTER (
            WHERE action IN ('approval_apply', 'export_create', 'recon_create', 'manual_review_request')
            AND (payload->>'latency_ms') IS NOT NULL
          ) AS p95_latency_ms
        FROM accounting_audit_events
        WHERE tenant = $1 AND ts >= $2
      `;
      const healthResult = await pool.query(healthQuery, [tenant, health5mFrom]);
      const health = healthResult.rows[0] || {
        success_count: 0,
        error_count: 0,
        total_count: 0,
        p95_latency_ms: null,
      };
      
      const success_rate_5m = health.total_count > 0
        ? health.success_count / health.total_count
        : 1.0;
      const error_rate_5m = health.total_count > 0
        ? health.error_count / health.total_count
        : 0.0;
      
      // 5. Engine 모드 집계 조회 (지난 24시간 기준) - R8-S2
      const engine24hFrom = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
      const engineQuery = `
        SELECT 
          (payload->>'engine_mode')::text AS engine_mode,
          COUNT(*) AS cnt
        FROM accounting_audit_events
        WHERE 
          tenant = $1
          AND action = 'postings_suggest'
          AND payload ? 'engine_mode'
          AND ts >= $2
        GROUP BY (payload->>'engine_mode')
      `;
      const engineResult = await pool.query(engineQuery, [tenant, engine24hFrom]);
      const engineRows = engineResult.rows || [];
      
      // Engine 섹션 빌드
      type EngineMode = 'mock' | 'rule' | 'local-llm' | 'remote';
      const counts: Record<EngineMode, number> = {
        mock: 0,
        rule: 0,
        'local-llm': 0,
        remote: 0,
      };
      
      for (const row of engineRows) {
        const mode = row.engine_mode as EngineMode;
        if (mode in counts) {
          // PostgreSQL COUNT(*)는 이미 숫자로 반환됨
          counts[mode] = typeof row.cnt === 'number' ? row.cnt : parseInt(String(row.cnt), 10) || 0;
        }
      }
      
      let primary_mode: EngineMode | null = null;
      let max = 0;
      for (const mode of Object.keys(counts) as EngineMode[]) {
        if (counts[mode] > max) {
          max = counts[mode];
          primary_mode = mode;
        }
      }
      
      res.json({
        window: {
          from: windowFromISO,
          to: windowToISO,
        },
        pilot: {
          suggest_calls: pilot.suggest_calls,
          top1_accuracy: Math.round(top1Accuracy * 100) / 100,
          manual_review_rate: Math.round(manualReviewRate * 100) / 100,
        },
        risk: {
          high_risk_24h: risk.high_risk_count || 0,
          medium_risk_24h: risk.medium_risk_count || 0,
          low_risk_24h: risk.low_risk_count || 0,
          manual_review_pending: queue.manual_review_pending,
        },
        health: {
          success_rate_5m: Math.round(success_rate_5m * 100) / 100,
          error_rate_5m: Math.round(error_rate_5m * 100) / 100,
          p95_latency_5m: health.p95_latency_ms ? Math.round(health.p95_latency_ms) : null,
        },
        queue: {
          offline_queue_backlog: 0, // 추후 확장
        },
        engine: {
          primary_mode: primary_mode,
          counts: counts,
        },
      });
    } catch (e: any) {
      console.error('[OS Dashboard] Error:', e);
      console.error('[OS Dashboard] Stack:', e?.stack);
      next(e);
    }
  }
);

export default router;

