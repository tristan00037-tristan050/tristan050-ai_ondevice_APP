/**
 * Config Distribution Service
 * Versioned config with rollback and ETag support
 */

import express from 'express';
import configsRouter from './api/configs';

const app = express();

app.use(express.json());

// API routes
app.use('/api/v1/configs', configsRouter);

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`Config Distribution Service listening on port ${PORT}`);
});

export default app;

