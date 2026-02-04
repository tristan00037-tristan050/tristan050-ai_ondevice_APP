/**
 * Control Plane API Server
 * Multi-tenant IAM foundation entry point
 */

import express from 'express';
import { requirePolicyHeaderBundle } from '../gateway/mw/policy_header_bundle';
import tenantsRouter from './api/tenants';
import usersRouter from './api/users';
import rolesRouter from './api/roles';
import auditRouter from './api/audit';

const app = express();

app.use(express.json());

// Policy header bundle validation (fail-closed for live requests)
app.use(requirePolicyHeaderBundle);

// API routes
app.use('/api/v1/iam/tenants', tenantsRouter);
app.use('/api/v1/iam/users', usersRouter);
app.use('/api/v1/iam/roles', rolesRouter);
app.use('/api/v1/audit/logs', auditRouter);

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Control Plane API server listening on port ${PORT}`);
});

export default app;

