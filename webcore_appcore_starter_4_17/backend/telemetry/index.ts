/**
 * Telemetry Service
 * Meta-only telemetry ingestion, storage, rollups, and alerting
 */

import express from 'express';
import { forbidMockModeNetwork } from '../gateway/mw/mock_network_zero_gate';
import { requireMetaOnly } from '../gateway/mw/meta_only_gate';
import { exportPreview, exportApprove } from './export_gate';
import ingestRouter from './api/ingest';
import alertsRouter from './api/alerts';

const app = express();

app.use(express.json());

// Mock mode network zero hard gate (must be first to block before other gates)
app.use(forbidMockModeNetwork);

// Apply meta-only gate to telemetry ingest endpoint (client -> server meta payload)
app.use('/api/v1/telemetry', requireMetaOnly);

// API routes
app.use('/api/v1/telemetry', ingestRouter);
app.use('/api/v1/telemetry/alerts', alertsRouter);

// Export 2-step: Preview → Approve (meta-only only)
app.post('/api/v1/export/preview', (req, res) => {
  const out = exportPreview(req.body);
  return res.status(out.status).json(out.json);
});

app.post('/api/v1/export/approve', (req, res) => {
  const out = exportApprove(req.body);
  return res.status(out.status).json(out.json);
});

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

const PORT = process.env.PORT || 3002;
app.listen(PORT, () => {
  console.log(`Telemetry Service listening on port ${PORT}`);
});

export default app;

