/**
 * Model Registry Service
 * Express app for Model Registry API
 */

import express from 'express';
import { requireCallerContext } from '../control_plane/services/auth_context';
import * as modelsApi from './api/models';
import * as versionsApi from './api/versions';
import * as artifactsApi from './api/artifacts';

const app = express();

// Middleware
app.use(express.json());
app.use(requireCallerContext);

// Model routes
app.post('/api/v1/models', modelsApi.createModelHandler);
app.get('/api/v1/models', modelsApi.listModelsHandler);
app.get('/api/v1/models/:modelId', modelsApi.getModelHandler);

// Model version routes
app.post('/api/v1/models/:modelId/versions', versionsApi.createModelVersionHandler);
app.get('/api/v1/models/:modelId/versions', versionsApi.listModelVersionsHandler);

// Artifact routes
app.post('/api/v1/models/:modelId/versions/:versionId/artifacts', artifactsApi.createArtifactHandler);
app.get('/api/v1/models/:modelId/versions/:versionId/artifacts', artifactsApi.listArtifactsHandler);

export default app;
