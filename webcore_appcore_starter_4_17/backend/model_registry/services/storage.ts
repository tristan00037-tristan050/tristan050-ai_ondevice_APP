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
    status: 'active',
    created_at: new Date(),
    updated_at: new Date(),
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
    version: data.version,
    status: 'draft',
    created_at: new Date(),
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
  // Fail-Closed: Model version must exist
  const version = modelVersions.find(
    v => v.id === modelVersionId
  );
  // Verify model belongs to tenant via model_id lookup
  const model = models.find(m => m.id === version?.model_id && m.tenant_id === tenantId);
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
    v => v.id === modelVersionId
  );
  if (!version) {
    throw new Error('Model version not found');
  }
  // Verify model belongs to tenant via model_id lookup
  const model = models.find(m => m.id === version.model_id && m.tenant_id === tenantId);
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
  const version = modelVersions.find(
    v => v.id === data.model_version_id && v.status === 'released'
  );
  // Verify model belongs to tenant
  const model = models.find(m => m.id === version?.model_id && m.tenant_id === tenantId);
  if (!model) {
    throw new Error('Model version not found or tenant mismatch');
  }
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

