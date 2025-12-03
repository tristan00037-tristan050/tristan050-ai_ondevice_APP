/**
 * 회계 BFF (Backend for Frontend)
 * Express 라우트: /postings, /approvals, /reconcile, /vat, /exports
 * 
 * @module bff-accounting
 */

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
app.use(osPolicyBridge()); // ★ OS 정책 헤더 브릿지
app.use(accessLog);
app.use(reqContext());
app.use(securityHeaders);
app.use(limitGeneral);
app.use(observeRequest);
app.use(cors());
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

app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'bff-accounting' }));

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
app.use(approvalsRouter);
app.use(exportsRouter);
app.use('/v1/accounting/reconciliation', reconciliationRouter);
app.use(auditRoute);
app.use(osSummaryRoute);

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
