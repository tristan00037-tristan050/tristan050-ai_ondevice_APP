/**
 * Config Service API Client
 * Rollout management: canary, kill switch, rollback
 */

export interface CanaryConfig {
  canary_percent: number;
  kill_switch: boolean;
  routing_seed?: string;
}

export interface ConfigReleaseRequest {
  config: CanaryConfig;
  environment: string;
}

export interface ConfigReleaseResponse {
  version: string;
  environment: string;
  released_at: string;
  released_by: string;
}

export interface ConfigRollbackRequest {
  environment: string;
  target_version?: string; // If not provided, rollback to previous version
}

export interface ConfigRollbackResponse {
  version: string;
  environment: string;
  rolled_back_at: string;
  rolled_back_by: string;
}

export interface ConfigGetResponse {
  config_type: string;
  environment: string;
  version: number;
  version_id: string;
  content: CanaryConfig;
  released_at: string;
  etag: string;
}

export interface ApiError {
  error: string;
  message: string;
  reason_code?: string;
}

/**
 * Config Service API Client
 */
export class ConfigApiClient {
  constructor(
    private baseUrl: string,
    private getAuthToken: () => string | null
  ) {}

  private async request<T>(
    method: string,
    path: string,
    body?: any
  ): Promise<T> {
    const token = this.getAuthToken();
    if (!token) {
      throw new Error('Authentication required');
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error: ApiError = await response.json().catch(() => ({
        error: 'Unknown error',
        message: `HTTP ${response.status}`,
        reason_code: response.status === 403 ? 'RBAC_PERMISSION_DENIED' : undefined,
      }));
      throw error;
    }

    return response.json();
  }

  /**
   * Get current config (with ETag)
   */
  async getConfig(environment: string): Promise<ConfigGetResponse> {
    const response = await this.request<ConfigGetResponse>(
      'GET',
      `/api/v1/configs/${environment}/canary`
    );
    // Map backend response to frontend format
    return {
      ...response,
      config: response.content as CanaryConfig,
      version: response.version.toString(),
    };
  }

  /**
   * Release config version
   * Creates a new version with the provided config and releases it
   */
  async releaseConfig(
    environment: string,
    config: CanaryConfig,
    tenantId: string
  ): Promise<ConfigReleaseResponse> {
    // First, create a new config version
    const createVersionResponse = await this.request<{ version_id: string; version: number }>(
      'POST',
      `/api/v1/configs/${environment}/canary:create-version`,
      {
        config_type: 'canary',
        environment,
        tenant_id: tenantId,
        content: config,
      }
    );

    // Then, release the version
    return this.request<ConfigReleaseResponse>(
      'POST',
      `/api/v1/configs/${environment}/canary:release`,
      {
        config_type: 'canary',
        environment,
        tenant_id: tenantId,
        version_id: createVersionResponse.version_id,
      }
    );
  }

  /**
   * Rollback config to previous version
   */
  async rollbackConfig(
    environment: string,
    tenantId: string,
    targetVersionId?: string
  ): Promise<ConfigRollbackResponse> {
    const rollbackResponse = await this.request<{ release: any }>(
      'POST',
      `/api/v1/configs/${environment}/canary:rollback`,
      {
        config_type: 'canary',
        environment,
        tenant_id: tenantId,
        to_version_id: targetVersionId || '', // If empty, rollback to previous
      }
    );

    return {
      version: rollbackResponse.release.version_id, // Use version_id as version string
      environment,
      rolled_back_at: rollbackResponse.release.released_at,
      rolled_back_by: rollbackResponse.release.released_by,
    };
  }
}

