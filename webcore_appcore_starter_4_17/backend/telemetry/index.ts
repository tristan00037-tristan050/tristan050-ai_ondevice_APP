/**
 * Telemetry Service
 * Meta-only telemetry ingestion, storage, rollups, and alerting
 */

import express from 'express';
import { requireMetaOnly } from '../gateway/mw/meta_only_gate';
import ingestRouter from './api/ingest';
import alertsRouter from './api/alerts';

const app = express();

app.use(express.json());

// Apply meta-only gate to telemetry ingest endpoint (client -> server meta payload)
app.use('/api/v1/telemetry', requireMetaOnly);

// API routes
app.use('/api/v1/telemetry', ingestRouter);
app.use('/api/v1/telemetry/alerts', alertsRouter);

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

const PORT = process.env.PORT || 3002;
app.listen(PORT, () => {
  console.log(`Telemetry Service listening on port ${PORT}`);
});

export default app;

