/**
 * Model Registry Storage Service
 * In-memory store (should be replaced with database in production)
 * Multi-tenant: all queries scoped by tenant_id
 */

import { Model, CreateModelRequest } from '../models/model';
import { ModelVersion, CreateModelVersionRequest } from '../models/version';
import { Artifact, CreateArtifactRequest } from '../models/artifact';
import { PersistMap } from '../services/persist_maps';

// Persistent stores (file-based, restart-safe)
const models = new PersistMap<Model>("models.json");
const modelVersions = new PersistMap<ModelVersion>("model_versions.json");
const artifacts = new PersistMap<Artifact>("artifacts.json");

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
  models.set(model.id, model);
  return model;
}

export function getModelById(tenantId: string, modelId: string): Model | null {
  const model = models.get(modelId);
  if (!model || model.tenant_id !== tenantId) {
    return null;
  }
  return model;
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
  modelVersions.set(version.id, version);
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

  const version = modelVersions.get(versionId);
  if (!version || version.model_id !== modelId) {
    return null;
  }
  return version;
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
  artifacts.set(artifact.id, artifact);
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

  const artifact = artifacts.get(artifactId);
  if (!artifact || artifact.model_version_id !== versionId) {
    return null;
  }
  return artifact;
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
  // Clear all entries from persistent maps
  for (const [key] of models.entries()) {
    models.delete(key);
  }
  for (const [key] of modelVersions.entries()) {
    modelVersions.delete(key);
  }
  for (const [key] of artifacts.entries()) {
    artifacts.delete(key);
  }
}

