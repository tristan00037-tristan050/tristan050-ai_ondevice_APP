/**
 * Model Registry Storage Service
 * In-memory store (should be replaced with database in production)
 * Multi-tenant: all queries scoped by tenant_id
 */

import { Model, CreateModelRequest } from '../models/model';
import { ModelVersion, CreateModelVersionRequest } from '../models/version';
import { Artifact, CreateArtifactRequest } from '../models/artifact';

// In-memory stores
const models: Model[] = [];
const modelVersions: ModelVersion[] = [];
const artifacts: Artifact[] = [];

/**
 * Model operations
 */
export function createModel(tenantId: string, request: CreateModelRequest): Model {
  const model: Model = {
    id: `model_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    tenant_id: tenantId,
    name: request.name,
    status: 'active',
    created_at: new Date(),
    updated_at: new Date(),
    metadata: request.metadata,
  };
  models.push(model);
  return model;
}

export function getModelById(tenantId: string, modelId: string): Model | null {
  const model = models.find(m => m.id === modelId && m.tenant_id === tenantId);
  return model || null;
}

export function listModels(tenantId: string): Model[] {
  return models.filter(m => m.tenant_id === tenantId);
}

/**
 * ModelVersion operations
 */
export function createModelVersion(
  tenantId: string,
  modelId: string,
  request: CreateModelVersionRequest
): ModelVersion | null {
  // Verify model exists and belongs to tenant
  const model = getModelById(tenantId, modelId);
  if (!model) {
    return null;
  }

  const version: ModelVersion = {
    id: `version_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    model_id: modelId,
    version: request.version,
    status: 'draft',
    created_at: new Date(),
    metadata: request.metadata,
  };
  modelVersions.push(version);
  return version;
}

export function getModelVersionById(
  tenantId: string,
  modelId: string,
  versionId: string
): ModelVersion | null {
  // Verify model belongs to tenant
  const model = getModelById(tenantId, modelId);
  if (!model) {
    return null;
  }

  const version = modelVersions.find(
    v => v.id === versionId && v.model_id === modelId
  );
  return version || null;
}

export function listModelVersions(tenantId: string, modelId: string): ModelVersion[] {
  // Verify model belongs to tenant
  const model = getModelById(tenantId, modelId);
  if (!model) {
    return [];
  }

  return modelVersions.filter(v => v.model_id === modelId);
}

/**
 * Artifact operations
 */
export function createArtifact(
  tenantId: string,
  modelId: string,
  versionId: string,
  request: CreateArtifactRequest
): Artifact | null {
  // Verify model version exists and belongs to tenant
  const version = getModelVersionById(tenantId, modelId, versionId);
  if (!version) {
    return null;
  }

  const artifact: Artifact = {
    id: `artifact_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    model_version_id: versionId,
    platform: request.platform,
    runtime: request.runtime,
    sha256: request.sha256,
    size_bytes: request.size_bytes,
    storage_ref: request.storage_ref,
    status: 'uploading',
    created_at: new Date(),
    metadata: request.metadata,
  };
  artifacts.push(artifact);
  return artifact;
}

export function getArtifactById(
  tenantId: string,
  modelId: string,
  versionId: string,
  artifactId: string
): Artifact | null {
  // Verify model version belongs to tenant
  const version = getModelVersionById(tenantId, modelId, versionId);
  if (!version) {
    return null;
  }

  const artifact = artifacts.find(
    a => a.id === artifactId && a.model_version_id === versionId
  );
  return artifact || null;
}

export function listArtifacts(
  tenantId: string,
  modelId: string,
  versionId: string
): Artifact[] {
  // Verify model version belongs to tenant
  const version = getModelVersionById(tenantId, modelId, versionId);
  if (!version) {
    return [];
  }

  return artifacts.filter(a => a.model_version_id === versionId);
}

/**
 * Clear all data (for testing only)
 */
export function clearAll(): void {
  models.length = 0;
  modelVersions.length = 0;
  artifacts.length = 0;
}

