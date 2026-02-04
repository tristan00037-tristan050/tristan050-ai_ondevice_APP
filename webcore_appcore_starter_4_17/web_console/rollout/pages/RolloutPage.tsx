/**
 * Rollout Page
 * Manage canary rollout, kill switch, and rollback
 */

import React, { useState, useEffect } from 'react';
import { CanarySlider } from '../components/CanarySlider';
import { KillSwitchToggle } from '../components/KillSwitchToggle';
import { RollbackButton } from '../components/RollbackButton';
import { ConfigApiClient, CanaryConfig, ApiError } from '../../api_client/config_api';

interface RolloutPageProps {
  environment: string;
  tenantId: string;
  configApiClient: ConfigApiClient;
}

export const RolloutPage: React.FC<RolloutPageProps> = ({
  environment,
  tenantId,
  configApiClient,
}) => {
  const [canaryPercent, setCanaryPercent] = useState(0);
  const [killSwitch, setKillSwitch] = useState(false);
  const [currentVersion, setCurrentVersion] = useState<string | null>(null);
  const [previousVersion, setPreviousVersion] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isApplying, setIsApplying] = useState(false);

  // Load current config
  useEffect(() => {
    loadConfig();
  }, [environment]);

  const loadConfig = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const config = await configApiClient.getConfig(environment);
      setCanaryPercent(config.config.canary_percent);
      setKillSwitch(config.config.kill_switch);
      setCurrentVersion(config.version);
      // Note: Previous version would come from version history API
      // For now, we'll set it to null
      setPreviousVersion(null);
    } catch (err: any) {
      const apiError = err as ApiError;
      setError(apiError.reason_code || apiError.message || 'Failed to load config');
    } finally {
      setIsLoading(false);
    }
  };

  const handleApply = async () => {
    setIsApplying(true);
    setError(null);
    setSuccess(null);

    try {
      const newConfig: CanaryConfig = {
        canary_percent: canaryPercent,
        kill_switch: killSwitch,
      };

      const result = await configApiClient.releaseConfig(environment, newConfig, tenantId);
      setCurrentVersion(result.version);
      setSuccess(`Config released successfully (version: ${result.version})`);
      
      // Reload config to reflect new state
      await loadConfig();
    } catch (err: any) {
      const apiError = err as ApiError;
      setError(apiError.reason_code || apiError.message || 'Failed to apply config');
    } finally {
      setIsApplying(false);
    }
  };

  const handleRollback = async () => {
    setError(null);
    setSuccess(null);

    try {
      const result = await configApiClient.rollbackConfig(environment, tenantId);
      setCurrentVersion(result.version);
      setSuccess(`Config rolled back successfully (version: ${result.version})`);
      
      // Reload config to reflect new state
      await loadConfig();
    } catch (err: any) {
      const apiError = err as ApiError;
      throw new Error(apiError.reason_code || apiError.message || 'Rollback failed');
    }
  };

  if (isLoading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="rollout-page">
      <h1>Rollout Management - {environment}</h1>

      {error && (
        <div className="error" role="alert">
          Error: {error}
        </div>
      )}

      {success && (
        <div className="success" role="alert">
          {success}
        </div>
      )}

      <div className="rollout-controls">
        <div className="control-group">
          <CanarySlider
            value={canaryPercent}
            onChange={setCanaryPercent}
            disabled={isApplying}
          />
        </div>

        <div className="control-group">
          <KillSwitchToggle
            enabled={killSwitch}
            onChange={setKillSwitch}
            disabled={isApplying}
          />
        </div>

        <div className="control-group">
          <button
            onClick={handleApply}
            disabled={isApplying}
            className="btn-apply"
          >
            {isApplying ? 'Applying...' : 'Apply Changes'}
          </button>
        </div>

        <div className="control-group">
          <RollbackButton
            onRollback={handleRollback}
            disabled={isApplying}
            currentVersion={currentVersion || undefined}
            previousVersion={previousVersion || undefined}
          />
        </div>
      </div>

      {currentVersion && (
        <div className="version-info">
          <p>Current Version: {currentVersion}</p>
        </div>
      )}
    </div>
  );
};

