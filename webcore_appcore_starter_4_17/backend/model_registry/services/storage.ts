/**
 * Storage Service
 * Artifact storage and metadata management
 * Immutable released artifacts
 */

import { Model, ModelVersion, Artifact, ReleasePointer } from '../models/model';
import { SigningKey } from './signing';

// In-memory stores (should be replaced with database in production)
const models: Model[] = [];
const modelVersions: ModelVersion[] = [];
const artifacts: Artifact[] = [];
const releasePointers: ReleasePointer[] = [];
const signingKeys: SigningKey[] = [];

// Export for API access
export { models, modelVersions, artifacts, releasePointers };

/**
 * Initialize default signing key (for v1)
 */
export function initializeSigningKey(): SigningKey {
  const { generateKeyPair } = require('./signing');
  const { publicKey, privateKey } = generateKeyPair();
  
  const key: SigningKey = {
    key_id: 'v1-default',
    public_key: publicKey,
    private_key: privateKey,
    created_at: new Date(),
    active: true,
  };
  
  signingKeys.push(key);
  return key;
}

/**
 * Get active signing key
 */
export function getActiveSigningKey(): SigningKey | null {
  const activeKey = signingKeys.find(k => k.active);
  if (!activeKey) {
    return initializeSigningKey();
  }
  return activeKey;
}

/**
 * Create model
 */
export function createModel(tenantId: string, userId: string, data: {
  name: string;
  description?: string;
  metadata?: Record<string, any>;
}): Model {
  const model: Model = {
    id: `model_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    tenant_id: tenantId,
    name: data.name,
    description: data.description,
    status: 'draft',
    created_at: new Date(),
    updated_at: new Date(),
    created_by: userId,
    metadata: data.metadata,
  };
  
  models.push(model);
  return model;
}

/**
 * Create model version
 */
export function createModelVersion(
  modelId: string,
  tenantId: string,
  userId: string,
  data: {
    version: string;
    metadata?: Record<string, any>;
  }
): ModelVersion {
  // Fail-Closed: Model must exist and belong to tenant
  const model = models.find(m => m.id === modelId && m.tenant_id === tenantId);
  if (!model) {
    throw new Error('Model not found');
  }
  
  const version: ModelVersion = {
    id: `version_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    model_id: modelId,
    tenant_id: tenantId,
    version: data.version,
    status: 'draft',
    created_at: new Date(),
    updated_at: new Date(),
    created_by: userId,
    metadata: data.metadata,
  };
  
  modelVersions.push(version);
  return version;
}

/**
 * Create artifact (with signature)
 */
export function createArtifact(
  modelVersionId: string,
  tenantId: string,
  userId: string,
  data: {
    platform: string;
    runtime: string;
    file_path: string;
    file_size: number;
    sha256: string;
    model_id: string;
    version: string;
  }
): Artifact {
  // Fail-Closed: Model version must exist and belong to tenant
  const version = modelVersions.find(
    v => v.id === modelVersionId && v.tenant_id === tenantId
  );
  if (!version) {
    throw new Error('Model version not found');
  }
  
  // Sign artifact
  const signingKey = getActiveSigningKey();
  if (!signingKey) {
    throw new Error('Signing key not available');
  }
  
  const { signArtifact } = require('./signing');
  const signature = signArtifact(
    data.sha256,
    data.model_id,
    data.version,
    data.platform,
    data.runtime,
    signingKey.private_key
  );
  
  const artifact: Artifact = {
    id: `artifact_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    model_version_id: modelVersionId,
    tenant_id: tenantId,
    platform: data.platform,
    runtime: data.runtime,
    file_path: data.file_path,
    file_size: data.file_size,
    sha256: data.sha256,
    signature,
    key_id: signingKey.key_id,
    created_at: new Date(),
    created_by: userId,
  };
  
  artifacts.push(artifact);
  return artifact;
}

/**
 * Release model version (immutable)
 */
export function releaseModelVersion(
  modelVersionId: string,
  tenantId: string,
  userId: string
): ModelVersion {
  const version = modelVersions.find(
    v => v.id === modelVersionId && v.tenant_id === tenantId
  );
  if (!version) {
    throw new Error('Model version not found');
  }
  
  // Fail-Closed: Cannot overwrite released version
  if (version.status === 'released') {
    throw new Error('Model version already released (immutable)');
  }
  
  version.status = 'released';
  version.updated_at = new Date();
  return version;
}

/**
 * Set release pointer (for delivery)
 */
export function setReleasePointer(
  modelId: string,
  tenantId: string,
  userId: string,
  data: {
    platform: string;
    runtime: string;
    model_version_id: string;
    artifact_id: string;
  }
): ReleasePointer {
  // Fail-Closed: Version must be released
  const version = modelVersions.find(
    v => v.id === data.model_version_id && v.tenant_id === tenantId && v.status === 'released'
  );
  if (!version) {
    throw new Error('Model version not released');
  }
  
  // Fail-Closed: Artifact must exist and match version
  const artifact = artifacts.find(
    a => a.id === data.artifact_id && a.model_version_id === data.model_version_id
  );
  if (!artifact) {
    throw new Error('Artifact not found or does not match version');
  }
  
  // Update or create release pointer
  let pointer = releasePointers.find(
    p => p.model_id === modelId && p.platform === data.platform && p.runtime === data.runtime
  );
  
  if (pointer) {
    pointer.model_version_id = data.model_version_id;
    pointer.artifact_id = data.artifact_id;
    pointer.updated_at = new Date();
  } else {
    pointer = {
      id: `pointer_${Date.now()}_${Math.random().toString(36).substring(7)}`,
      model_id: modelId,
      tenant_id: tenantId,
      platform: data.platform,
      runtime: data.runtime,
      model_version_id: data.model_version_id,
      artifact_id: data.artifact_id,
      created_at: new Date(),
      created_by: userId,
    };
    releasePointers.push(pointer);
  }
  
  return pointer;
}

/**
 * Get delivery information
 */
export function getDelivery(
  modelId: string,
  tenantId: string,
  platform: string,
  runtime: string
): {
  artifact: Artifact;
  version: ModelVersion;
  signingKey: SigningKey;
} | null {
  const pointer = releasePointers.find(
    p => p.model_id === modelId &&
         p.tenant_id === tenantId &&
         p.platform === platform &&
         p.runtime === runtime
  );
  
  if (!pointer) {
    return null;
  }
  
  const artifact = artifacts.find(a => a.id === pointer.artifact_id);
  const version = modelVersions.find(v => v.id === pointer.model_version_id);
  const signingKey = signingKeys.find(k => k.key_id === artifact?.key_id);
  
  if (!artifact || !version || !signingKey) {
    return null;
  }
  
  return { artifact, version, signingKey };
}

