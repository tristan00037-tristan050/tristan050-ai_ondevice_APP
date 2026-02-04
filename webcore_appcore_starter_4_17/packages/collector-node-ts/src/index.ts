/**
 * Collector 서버 메인 진입점
 * 모든 엔드포인트에 테넌트 가드 강제 적용
 * 
 * @module index
 */

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import reportsRouter from './routes/reports.js';
import { requireTenantAuth } from './mw/auth.js';
import { healthCheck as dbHealthCheck } from './db/client.js';
import * as reportsDb from './db/reports.js';
import { metrics, setDatabaseConnected, incrementReportIngested, observeResponseTime, incrementError } from './metrics/prometheus.js';
import { getCachedTimeline, setCachedTimeline, invalidateOnReportSave } from './cache/reports.js';
import { batchAggregateTimeline } from './db/batch.js';
import { auditMiddleware } from './mw/audit.js';
import { validateInput } from './mw/validation.js';
import { defaultRateLimiter } from './mw/rateLimit.js';
import { notifyDatabaseConnectionFailure } from './utils/notifications.js';

const app = express();
const PORT = process.env.PORT || 9090;

// 미들웨어
app.use(helmet());
app.use(cors());
app.use(express.json({ limit: '10mb' })); // Body 크기 제한

// 보안 미들웨어
app.use(auditMiddleware); // 감사 로그
app.use(validateInput); // 입력 검증
app.use(defaultRateLimiter); // Rate Limiting

// 루트 경로 - API 정보 제공
app.get('/', (req, res) => {
  res.json({
    service: 'collector',
    version: '0.1.0',
    endpoints: {
      health: '/health',
      metrics: '/metrics',
      reports: '/reports',
      timeline: '/timeline',
      ingest: '/ingest/qc',
      admin: '/admin/retention/run',
      audit: '/admin/audit/logs',
    },
    docs: '/docs/openapi.yaml',
  });
});

// Health check (인증 불필요)
app.get('/health', async (req, res) => {
  try {
    const dbHealthy = await dbHealthCheck();
    setDatabaseConnected(dbHealthy);
    
    if (!dbHealthy) {
      // 데이터베이스 연결 실패 알림
      await notifyDatabaseConnectionFailure(new Error('Database health check failed'));
    }
    
    res.json({
      status: dbHealthy ? 'ok' : 'degraded',
      service: 'collector',
      database: dbHealthy ? 'connected' : 'disconnected',
    });
  } catch (error) {
    await notifyDatabaseConnectionFailure(error as Error);
    res.status(503).json({
      status: 'degraded',
      service: 'collector',
      database: 'disconnected',
      error: 'Health check failed',
    });
  }
});

// Prometheus 메트릭 엔드포인트 (인증 불필요)
app.get('/metrics', (req, res) => {
  res.set('Content-Type', 'text/plain; version=0.0.4');
  res.send(metrics.export());
});

// Reports 라우터 (모든 엔드포인트에 requireTenantAuth 적용됨)
app.use('/reports', reportsRouter);

// Timeline 엔드포인트 (테넌트 가드 강제)
app.get('/timeline', requireTenantAuth, async (req, res) => {
  try {
    const windowH = parseInt(req.query.window_h as string) || 24;
    const tenantId = req.tenantId;
    
    if (!tenantId) {
      return res.status(401).json({ error: 'Tenant ID not found' });
    }

    // 캐시 조회
    const cacheKey = { tenantId, windowH };
    const cached = getCachedTimeline(cacheKey);
    if (cached) {
      return res.json(cached);
    }

    const now = Date.now();
    const windowMs = windowH * 3600000;
    const startTime = now - windowMs;
    const endTime = now;

    // 배치 집계를 사용하여 타임라인 생성 (SQL 직접 집계로 최적화)
    const bucketSizeMs = 3600000; // 1시간
    const buckets = await batchAggregateTimeline(tenantId, startTime, endTime, bucketSizeMs);

    const timeline = {
      window_h: windowH,
      buckets,
    };

    // 캐시 저장
    setCachedTimeline(cacheKey, timeline);

    res.json(timeline);
  } catch (error) {
    console.error('Error fetching timeline:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Ingest 엔드포인트 (테넌트 가드 강제)
app.post('/ingest/qc', requireTenantAuth, async (req, res) => {
  const startTime = Date.now();
  try {
    const tenantId = req.tenantId;
    
    if (!tenantId) {
      observeResponseTime('/ingest/qc', Date.now() - startTime, 401);
      incrementError('/ingest/qc', 401);
      return res.status(401).json({ error: 'Tenant ID not found' });
    }
    const report = req.body;

    // Ajv 검증 (실제로는 스키마 파일 로드)
    // 여기서는 간단히 구조 확인
    if (!report || !report.status) {
      observeResponseTime('/ingest/qc', Date.now() - startTime, 400);
      incrementError('/ingest/qc', 400);
      return res.status(400).json({ error: 'Invalid report format' });
    }

    // 리포트 저장 (데이터베이스)
    const reportId = `report-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    await reportsDb.saveReport({
      id: reportId,
      tenantId,
      report,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    });

    // 리포트 저장 시 관련 캐시 무효화
    invalidateOnReportSave(tenantId);

    incrementReportIngested(tenantId);
    observeResponseTime('/ingest/qc', Date.now() - startTime, 201);

    res.status(201).json({
      id: reportId,
      status: 'ingested',
    });
  } catch (error) {
    console.error('Error ingesting report:', error);
    observeResponseTime('/ingest/qc', Date.now() - startTime, 500);
    incrementError('/ingest/qc', 500);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// 감사 로그 조회 엔드포인트 (관리자용)
app.get('/admin/audit/logs', requireTenantAuth, async (req, res) => {
  try {
    const tenantId = req.tenantId;
    if (!tenantId) {
      return res.status(401).json({ error: 'Tenant ID not found' });
    }

    const { getAuditLogs } = await import('./mw/audit.js');
    const startTime = req.query.start_time ? parseInt(req.query.start_time as string) : undefined;
    const endTime = req.query.end_time ? parseInt(req.query.end_time as string) : undefined;
    const securityEvent = req.query.security_event === 'true';
    const limit = req.query.limit ? parseInt(req.query.limit as string) : 100;

    const logs = getAuditLogs(
      {
        tenantId,
        startTime,
        endTime,
        securityEvent,
      },
      limit
    );

    res.json({
      logs,
      count: logs.length,
    });
  } catch (error) {
    console.error('Error fetching audit logs:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Retention 관리 엔드포인트 (테넌트 가드 강제)
app.post('/admin/retention/run', requireTenantAuth, async (req, res) => {
  try {
    const tenantId = req.tenantId;
    
    if (!tenantId) {
      return res.status(401).json({ error: 'Tenant ID not found' });
    }
    const retainDays = parseInt(process.env.RETAIN_DAYS || '30');
    const cutoffTime = Date.now() - (retainDays * 24 * 3600000);

    // 데이터베이스에서 오래된 리포트 삭제
    const deleted = await reportsDb.deleteReports(tenantId, cutoffTime);

    res.json({
      tenantId,
      retainDays,
      deleted,
      cutoffTime,
    });
  } catch (error) {
    console.error('Error running retention:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// 서버 시작
app.listen(PORT, () => {
  console.log(`Collector server running on port ${PORT}`);
  console.log(`API_KEYS: ${process.env.API_KEYS || 'not set'}`);
});

export default app;

