/**
 * Config Storage Service
 * Versioned config storage with rollback support
 */

import { ConfigVersion, ConfigRelease, ConfigType, Environment } from '../models/config';
import crypto from 'crypto';

// In-memory store (should be replaced with database in production)
const configVersions: ConfigVersion[] = [];
const configReleases: ConfigRelease[] = [];

/**
 * Create config version
 * Immutable: once created, cannot be modified
 */
export function createConfigVersion(
  request: Omit<ConfigVersion, 'id' | 'version' | 'created_at'>
): ConfigVersion {
  // Get next version number for this config_type + environment + tenant
  const existingVersions = configVersions.filter(
    v => v.config_type === request.config_type &&
         v.environment === request.environment &&
         v.tenant_id === request.tenant_id
  );
  const nextVersion = existingVersions.length > 0
    ? Math.max(...existingVersions.map(v => v.version)) + 1
    : 1;

  const version: ConfigVersion = {
    id: `config_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    config_type: request.config_type,
    environment: request.environment,
    version: nextVersion,
    content: request.content,
    created_at: new Date(),
    created_by: request.created_by,
    tenant_id: request.tenant_id,
    metadata: request.metadata,
  };

  configVersions.push(version);
  return version;
}

/**
 * Get config version by ID
 * Fail-Closed: cross-tenant access blocked
 */
export function getConfigVersion(
  versionId: string,
  tenantId: string
): ConfigVersion | null {
  const version = configVersions.find(v => v.id === versionId);
  if (!version) {
    return null;
  }

  // Fail-Closed: Cross-tenant access blocked
  if (version.tenant_id !== tenantId) {
    return null;
  }

  return version;
}

/**
 * List config versions
 * Fail-Closed: cross-tenant access blocked
 */
export function listConfigVersions(
  configType: ConfigType,
  environment: Environment,
  tenantId: string
): ConfigVersion[] {
  return configVersions.filter(
    v => v.config_type === configType &&
         v.environment === environment &&
         v.tenant_id === tenantId
  ).sort((a, b) => b.version - a.version); // Latest first
}

/**
 * Release config version
 * Creates a release record pointing to a version
 */
export function releaseConfig(
  request: Omit<ConfigRelease, 'id' | 'released_at' | 'status'>
): ConfigRelease {
  // Fail-Closed: Version must exist and belong to tenant
  const version = getConfigVersion(request.version_id, request.tenant_id);
  if (!version) {
    throw new Error('Config version not found or cross-tenant access denied');
  }

  // Fail-Closed: Version must match config_type and environment
  if (version.config_type !== request.config_type || version.environment !== request.environment) {
    throw new Error('Config version mismatch');
  }

  // Mark previous release as rolled_back if exists
  const previousRelease = configReleases.find(
    r => r.config_type === request.config_type &&
         r.environment === request.environment &&
         r.tenant_id === request.tenant_id &&
         r.status === 'active'
  );
  if (previousRelease) {
    previousRelease.status = 'rolled_back';
  }

  const release: ConfigRelease = {
    id: `release_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    config_type: request.config_type,
    environment: request.environment,
    version_id: request.version_id,
    released_at: new Date(),
    released_by: request.released_by,
    tenant_id: request.tenant_id,
    status: 'active',
  };

  configReleases.push(release);
  return release;
}

/**
 * Rollback config to previous version
 */
export function rollbackConfig(
  request: Omit<ConfigRelease, 'id' | 'released_at' | 'status' | 'rollback_to_version_id'> & { to_version_id: string }
): ConfigRelease {
  // Fail-Closed: Target version must exist and belong to tenant
  const targetVersion = getConfigVersion(request.to_version_id, request.tenant_id);
  if (!targetVersion) {
    throw new Error('Target config version not found or cross-tenant access denied');
  }

  // Fail-Closed: Version must match config_type and environment
  if (targetVersion.config_type !== request.config_type || targetVersion.environment !== request.environment) {
    throw new Error('Config version mismatch');
  }

  // Mark current release as rolled_back
  const currentRelease = configReleases.find(
    r => r.config_type === request.config_type &&
         r.environment === request.environment &&
         r.tenant_id === request.tenant_id &&
         r.status === 'active'
  );
  if (currentRelease) {
    currentRelease.status = 'rolled_back';
    currentRelease.rollback_to_version_id = request.to_version_id;
  }

  // Create new release pointing to rollback version
  const release: ConfigRelease = {
    id: `release_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    config_type: request.config_type,
    environment: request.environment,
    version_id: request.to_version_id,
    released_at: new Date(),
    released_by: request.released_by,
    tenant_id: request.tenant_id,
    status: 'active',
    rollback_to_version_id: currentRelease?.version_id,
  };

  configReleases.push(release);
  return release;
}

/**
 * Get active release
 * Returns the currently active release for a config
 */
export function getActiveRelease(
  configType: ConfigType,
  environment: Environment,
  tenantId: string
): ConfigRelease | null {
  const release = configReleases.find(
    r => r.config_type === configType &&
         r.environment === environment &&
         r.tenant_id === tenantId &&
         r.status === 'active'
  );

  if (!release) {
    return null;
  }

  // Fail-Closed: Cross-tenant access blocked
  if (release.tenant_id !== tenantId) {
    return null;
  }

  return release;
}

/**
 * Calculate ETag for config content
 * Deterministic: same content => same ETag
 */
export function calculateETag(content: Record<string, unknown>): string {
  const contentStr = JSON.stringify(content);
  const hash = crypto.createHash('sha256').update(contentStr).digest('hex');
  return `"${hash.substring(0, 16)}"`; // ETag format with quotes
}

/**
 * Clear storage (for testing only)
 */
export function clearStorage(): void {
  configVersions.length = 0;
  configReleases.length = 0;
}

