/**
 * 회계 BFF (Backend for Frontend)
 * Express 라우트: /postings, /approvals, /reconcile, /vat, /exports
 * 
 * @module bff-accounting
 */

// .env 파일 로드 (개발 환경)
import { config } from 'dotenv';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 프로젝트 루트의 .env 파일 로드
config({ path: resolve(__dirname, '../../../.env') });

// OpenTelemetry 초기화 (환경 변수로 활성화)
if (process.env.OTEL_ENABLED === '1') {
  await import('./otel.js');
}

import express from 'express';
import cors from 'cors';
import suggestRouter from './routes/suggest.js';
import approvalsRouter from './routes/approvals.js';
import exportsRouter from './routes/exports.js';
import reconciliationRouter from './routes/reconciliation.js';
import auditRoute from './routes/audit.js';
import osSummaryRoute from './routes/os-summary.js';
import osSourcesRoute from './routes/os-sources.js';
import osMetricsRoute from './routes/os-metrics.js';
import osDashboardRoute from './routes/os-dashboard.js';
import csOsDashboardRoute from './routes/cs-os-dashboard.js';
import csTicketsRoute from './routes/cs-tickets.js';
import riskRoute from './routes/risk.js';
import manualReviewRoute from './routes/manual-review.js';
import osLlmUsageRoute from './routes/os-llm-usage.js';
import { requestId } from './middleware/requestId.js';
import { accessLog } from './middleware/accessLog.js';
import { errorHandler } from './middleware/errorHandler.js';
import { reqContext } from './middleware/context.js';
import { securityHeaders, limitGeneral, limitApprovals, limitExports, limitRecon } from './middleware/security.js';
import { observeRequest, metricsHandler } from './middleware/metrics.js';
import { osPolicyBridge } from './middleware/osPolicyBridge.js';
import { ping as pgPing } from '@appcore/data-pg';

const app = express();
const PORT = process.env.PORT || 8081;

// trust proxy (LB 뒤 IP 식별)
app.set('trust proxy', 1);

// 공통 미들웨어
app.use(requestId);

// 1) 관찰/로그 이전에 CORS
app.use(cors({
  origin: process.env.CORS_ORIGIN || true,  // dev에서는 true
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: [
    'Content-Type',
    'Authorization',
    'X-Tenant',
    'X-Api-Key',
    'Idempotency-Key',
    'X-User-Role',
    'X-User-Id',
  ],
}));

// 2) Health Check 엔드포인트 (인증 불필요, osPolicyBridge 이전에 정의)
app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'bff-accounting' }));
app.get('/healthz', (_req, res) => res.json({ status: 'ok', timestamp: new Date().toISOString() }));

// k8s/런타임 준비상태 확인용 간단 엔드포인트
// /ready 강화: USE_PG=1 이면 PG 핑까지 검사
app.get('/ready', async (_req, res) => {
  if (process.env.USE_PG === '1') {
    try {
      const ok = await Promise.race([
        pgPing(),
        new Promise<boolean>((_, rej) => setTimeout(() => rej(new Error('pg_timeout')), 800)),
      ]);
      if (!ok) return res.status(503).send('pg_not_ready');
    } catch {
      return res.status(503).send('pg_not_ready');
    }
  }
  res.status(200).send('ok');
});

app.get('/readyz', async (_req, res) => {
  try {
    // DB 연결 체크
    const { pool } = await import('@appcore/data-pg');
    const dbCheck = await pool.query('SELECT 1 as health');
    if (dbCheck.rows.length === 0) {
      return res.status(503).json({
        status: 'unhealthy',
        reason: 'database_connection_failed',
        timestamp: new Date().toISOString(),
      });
    }
    
    // 기본 테이블 존재 확인
    await pool.query('SELECT COUNT(*) FROM accounting_audit_events LIMIT 1');
    
    res.json({
      status: 'ready',
      database: 'connected',
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    res.status(503).json({
      status: 'unhealthy',
      reason: 'database_error',
      error: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// 3) 요청/응답 로깅
app.use(observeRequest);

// 4) OS 정책 브리지 (이제 CORS 이후에 옴)
app.use(osPolicyBridge());

// 5) 보안 헤더
app.use(securityHeaders);

// 6) 컨텍스트, 레이트리밋
app.use(accessLog);
app.use(reqContext());
app.use(limitGeneral);
app.use(express.json({ limit: '10mb' }));

// 라우트 전용 레이트리밋
app.use('/v1/accounting/approvals', limitApprovals);
app.use('/v1/accounting/exports', limitExports);
app.use('/v1/accounting/reconciliation', limitRecon);

// Placeholder routes for R6-S1
app.get('/', (req, res) => {
  res.json({
    service: 'bff-accounting',
    version: '0.1.0',
    endpoints: {
      health: '/health',
      postings: '/v1/accounting/postings',
      approvals: '/v1/accounting/approvals',
      reconcile: '/v1/accounting/reconcile',
      vat: '/v1/accounting/vat',
      exports: '/v1/accounting/exports',
    },
  });
});


// 메트릭 엔드포인트 (클러스터 내부 스크레이프 용)
app.get('/metrics', async (req, res, next) => {
  try {
    await metricsHandler(req, res);
  } catch (err) {
    next(err);
  }
});

// 회계 라우트
app.use('/v1/accounting/postings', suggestRouter);
app.use('/v1/accounting/approvals', approvalsRouter);
app.use('/v1/accounting/exports', exportsRouter);
app.use('/v1/accounting/reconciliation', reconciliationRouter);
app.use(auditRoute);
app.use(osSummaryRoute);
app.use(osSourcesRoute);
app.use(osMetricsRoute);
app.use('/v1/accounting/os', osDashboardRoute);
app.use('/v1/cs', csTicketsRoute);
app.use('/v1/cs/os', csOsDashboardRoute);
app.use(osLlmUsageRoute); // R10-S1: LLM Usage Audit 라우트
app.use(riskRoute);
app.use(manualReviewRoute);
// healthRoute는 이미 /healthz, /readyz로 위에서 정의했으므로 제거
// app.use(healthRoute);

// 표준 에러 핸들러 (라우트 뒤에)
app.use(errorHandler);

// 서버 기동 및 그레이스풀 셧다운
const server = app.listen(PORT, () => {
  console.log(`bff-accounting on :${PORT}`);
});

process.on('SIGTERM', () => {
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 8000);
});

export default app;
