/**
 * Model Registry Service
 * Main entry point
 */

import express from 'express';
import { requireAuthAndContext } from '../control_plane/auth/middleware';
import modelsRouter from './api/models';

const app = express();

app.use(express.json());

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

// Model Registry API
app.use('/api/v1/models', requireAuthAndContext, modelsRouter);

const PORT = process.env.PORT || 3003;

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Model Registry service listening on port ${PORT}`);
  });
}

export default app;

