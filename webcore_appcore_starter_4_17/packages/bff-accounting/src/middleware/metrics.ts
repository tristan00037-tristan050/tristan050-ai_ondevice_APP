/**
 * Prometheus 메트릭 수집 미들웨어
 * 
 * @module bff-accounting/middleware/metrics
 */

import { Histogram, collectDefaultMetrics, Registry } from 'prom-client';
import type { Request, Response, NextFunction } from 'express';

const registry = new Registry();
collectDefaultMetrics({ register: registry, prefix: 'bff_' });

const httpDuration = new Histogram({
  name: 'http_request_duration_seconds',
  help: 'HTTP request duration',
  labelNames: ['method', 'route', 'status'],
  buckets: [0.05, 0.1, 0.2, 0.5, 1, 2, 5],
});

registry.registerMetric(httpDuration);

export async function metricsHandler(_req: Request, res: Response) {
  res.set('Content-Type', registry.contentType);
  const metrics = await registry.metrics();
  res.end(metrics);
}

export function observeRequest(req: Request, res: Response, next: NextFunction) {
  const start = process.hrtime.bigint();
  res.on('finish', () => {
    const diff = Number(process.hrtime.bigint() - start) / 1e9;
    httpDuration
      .labels(req.method, req.route?.path ?? req.path, String(res.statusCode))
      .observe(diff);
  });
  next();
}

