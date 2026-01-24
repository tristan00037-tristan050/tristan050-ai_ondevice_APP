/**
 * Storage Service
 * Artifact storage and metadata management
 * Immutable released artifacts
 */

import { Model } from '../models/model';
import { ModelVersion } from '../models/version';
import { Artifact } from '../models/artifact';
import { ReleasePointer } from '../models/release';
import { SigningKey } from './signing';
import { canonicalizeJson } from '../../../../packages/common/src/canon/jcs';
import { sign } from './signing';
import { getRegistryStore } from '../store';

// Use IRegistryStore interface instead of direct PersistMap access
const store = getRegistryStore();
// Signing keys remain in-memory for now (security-sensitive)
const signingKeys: SigningKey[] = [];

// Legacy exports for backward compatibility (deprecated, use store interface)
// These will be removed in future refactoring
export const models = {
  get: (id: string) => store.getModel(id),
  set: (id: string, model: Model) => store.putModel(id, model),
  find: (predicate: (m: Model) => boolean) => store.listModels().find(predicate),
  filter: (predicate: (m: Model) => boolean) => store.listModels().filter(predicate),
  values: () => store.listModels(),
  entries: () => store.listModels().map((m: Model) => [m.id, m] as [string, Model]),
};
export const modelVersions = {
  get: (id: string) => store.getModelVersion(id),
  set: (id: string, mv: ModelVersion) => store.putModelVersion(id, mv),
  find: (predicate: (mv: ModelVersion) => boolean) => store.listModelVersions().find(predicate),
  filter: (predicate: (mv: ModelVersion) => boolean) => store.listModelVersions().filter(predicate),
  values: () => store.listModelVersions(),
  entries: () => store.listModelVersions().map((mv: ModelVersion) => [mv.id, mv] as [string, ModelVersion]),
};
export const artifacts = {
  get: (id: string) => store.getArtifact(id),
  set: (id: string, a: Artifact) => store.putArtifact(id, a),
  find: (predicate: (a: Artifact) => boolean) => store.listArtifacts().find(predicate),
  filter: (predicate: (a: Artifact) => boolean) => store.listArtifacts().filter(predicate),
  values: () => store.listArtifacts(),
  entries: () => store.listArtifacts().map((a: Artifact) => [a.id, a] as [string, Artifact]),
};
export const releasePointers = {
  get: (id: string) => store.getReleasePointer(id),
  set: (id: string, rp: ReleasePointer) => store.putReleasePointer(id, rp),
  find: (predicate: (rp: ReleasePointer) => boolean) => store.listReleasePointers().find(predicate),
  filter: (predicate: (rp: ReleasePointer) => boolean) => store.listReleasePointers().filter(predicate),
  values: () => store.listReleasePointers(),
  entries: () => store.listReleasePointers().map((rp: ReleasePointer) => [rp.id, rp] as [string, ReleasePointer]),
};

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
    status: 'active',
    created_at: new Date(),
    updated_at: new Date(),
    metadata: data.metadata,
  };
  
  store.putModel(model.id, model);
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
  const model = store.getModel(modelId);
  if (!model || model.tenant_id !== tenantId) {
    throw new Error('Model not found');
  }
  if (!model) {
    throw new Error('Model not found');
  }
  
  const version: ModelVersion = {
    id: `version_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    model_id: modelId,
    version: data.version,
    status: 'draft',
    created_at: new Date(),
    metadata: data.metadata,
  };
  
  store.putModelVersion(version.id, version);
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
  // Fail-Closed: Model version must exist
  const version = store.getModelVersion(modelVersionId);
  // Verify model belongs to tenant via model_id lookup
  const model = version ? store.getModel(version.model_id) : null;
  if (!model || model.tenant_id !== tenantId) {
    throw new Error('Model version not found or tenant mismatch');
  }
  if (!model) {
    throw new Error('Model version not found or tenant mismatch');
  }
  if (!version) {
    throw new Error('Model version not found');
  }
  
  // Note: Artifact signature is not created here - it's created during delivery
  // This function just creates the artifact record
  
  const artifact: Artifact = {
    id: `artifact_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    model_version_id: modelVersionId,
    platform: data.platform,
    runtime: data.runtime,
    sha256: data.sha256,
    size_bytes: data.file_size,
    storage_ref: data.file_path,
    status: 'ready',
    created_at: new Date(),
  };
  
  store.putArtifact(artifact.id, artifact);
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
  const version = store.getModelVersion(modelVersionId);
  if (!version) {
    throw new Error('Model version not found');
  }
  // Verify model belongs to tenant via model_id lookup
  const model = store.getModel(version.model_id);
  if (!model || model.tenant_id !== tenantId) {
    throw new Error('Model version not found or tenant mismatch');
  }
  if (!model) {
    throw new Error('Model version not found or tenant mismatch');
  }
  
  // Fail-Closed: Cannot overwrite released version
  if (version.status === 'released') {
    throw new Error('Model version already released (immutable)');
  }
  
  version.status = 'released';
  version.released_at = new Date();
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
  const version = store.getModelVersion(data.model_version_id);
  if (!version || version.status !== 'released') {
    throw new Error('Model version not released');
  }
  // Verify model belongs to tenant
  const model = store.getModel(version.model_id);
  if (!model || model.tenant_id !== tenantId) {
    throw new Error('Model version not found or tenant mismatch');
  }
  
  // Fail-Closed: Artifact must exist and match version
  const artifact = store.getArtifact(data.artifact_id);
  if (!artifact || artifact.model_version_id !== data.model_version_id) {
    throw new Error('Artifact not found or does not match version');
  }
  
  // Update or create release pointer
  let pointer = store.listReleasePointers().find(
    p => p.model_id === modelId && p.platform === data.platform && p.runtime === data.runtime
  );
  
  if (pointer) {
    pointer.model_version_id = data.model_version_id;
    pointer.artifact_id = data.artifact_id;
    pointer.updated_at = new Date();
    // Update in persistent store
    store.putReleasePointer(pointer.id, pointer);
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
    store.putReleasePointer(pointer.id, pointer);
  }
  
  return pointer;
}

/**
 * Get delivery information with signature
 * Returns delivery response with required signature fields (sha256, signature, key_id, ts_ms, expires_at)
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
  // Signature fields (required for delivery response)
  sha256: string;
  signature: string;
  key_id: string;
  ts_ms: number;
  expires_at: number;
} | null {
  const pointer = store.listReleasePointers().find(
    (p: ReleasePointer) => p.model_id === modelId &&
         p.tenant_id === tenantId &&
         p.platform === platform &&
         p.runtime === runtime
  );
  
  if (!pointer) {
    return null;
  }
  
  const artifact = store.getArtifact(pointer.artifact_id);
  const version = store.getModelVersion(pointer.model_version_id);
  const signingKey = signingKeys.find(k => k.active) || (signingKeys.length > 0 ? signingKeys[0] : null);
  
  if (!artifact || !version || !signingKey) {
    return null;
  }

  // Create canonical payload for delivery
  const ts_ms = Date.now();
  const expires_at = ts_ms + (7 * 24 * 60 * 60 * 1000); // 7 days from now
  
  const canonicalPayload = canonicalizeJson({
    v: 'v1',
    ts_ms,
    tenant_id: tenantId,
    op: 'DELIVERY',
    body: {
      model_id: modelId,
      version_id: version.id,
      artifact_id: artifact.id,
      sha256: artifact.sha256,
      platform: artifact.platform,
      runtime: artifact.runtime,
    },
  });

  // Sign the canonical payload using crypto directly
  // Note: signingKey.private_key is base64-encoded PEM, need to decode first
  const crypto = require('crypto');
  let privateKey;
  try {
    // Try decoding base64 to PEM
    const privateKeyPem = Buffer.from(signingKey.private_key, 'base64').toString('utf-8');
    privateKey = crypto.createPrivateKey({
      key: privateKeyPem,
      format: 'pem',
      type: 'pkcs8',
    });
  } catch (error) {
    // If that fails, try using the key directly (might already be PEM)
    privateKey = crypto.createPrivateKey({
      key: signingKey.private_key,
      format: 'pem',
      type: 'pkcs8',
    });
  }
  const signatureBuffer = crypto.sign(null, Buffer.from(canonicalPayload, 'utf-8'), privateKey);
  const signature = signatureBuffer.toString('base64');
  
  return {
    artifact,
    version,
    signingKey,
    sha256: artifact.sha256,
    signature,
    key_id: signingKey.key_id,
    ts_ms,
    expires_at,
  };
}

