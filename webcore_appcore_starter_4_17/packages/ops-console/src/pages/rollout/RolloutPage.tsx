/**
 * RolloutPage (ops-console 통합)
 * Canary rollout, kill switch, rollback — self-contained with mock ConfigApiClient
 */

import React, { useState, useEffect } from 'react';

// ─── Inline types (external config_api not available in ops-console) ───────────

interface CanaryConfig {
  canary_percent: number;
  kill_switch: boolean;
}

interface ConfigResult {
  version: string;
  config: CanaryConfig;
}

// Mock state — persists across getConfig/releaseConfig/rollbackConfig calls
const mockState: { version: string; canary_percent: number; kill_switch: boolean } = {
  version: 'v1.0.0',
  canary_percent: 10,
  kill_switch: false,
};

// Mock ConfigApiClient — replace with real implementation when backend is ready
const mockConfigApiClient = {
  async getConfig(_env: string): Promise<ConfigResult> {
    return {
      version: mockState.version,
      config: { canary_percent: mockState.canary_percent, kill_switch: mockState.kill_switch },
    };
  },
  async releaseConfig(_env: string, config: CanaryConfig, _tenantId: string): Promise<{ version: string }> {
    const ts = Date.now();
    mockState.canary_percent = config.canary_percent;
    mockState.kill_switch = config.kill_switch;
    mockState.version = `v1.0.${ts}`;
    return { version: mockState.version };
  },
  async rollbackConfig(_env: string, _tenantId: string): Promise<{ version: string }> {
    mockState.canary_percent = 0;
    mockState.kill_switch = false;
    mockState.version = 'v1.0.0';
    return { version: mockState.version };
  },
};

// ─── CanarySlider ─────────────────────────────────────────────────────────────

const CanarySlider: React.FC<{
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}> = ({ value, onChange, disabled }) => (
  <div>
    <div className="flex items-center justify-between mb-2">
      <label className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
        Canary Traffic
      </label>
      <span className="text-sm font-bold text-indigo-600">{value}%</span>
    </div>
    <input
      type="range"
      min={0}
      max={100}
      step={5}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      disabled={disabled}
      className="w-full accent-indigo-600 disabled:opacity-40"
    />
    <div className="flex justify-between text-xs text-gray-300 mt-1">
      <span>0%</span>
      <span>50%</span>
      <span>100%</span>
    </div>
  </div>
);

// ─── KillSwitchToggle ────────────────────────────────────────────────────────

const KillSwitchToggle: React.FC<{
  enabled: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}> = ({ enabled, onChange, disabled }) => (
  <div className="flex items-center justify-between">
    <div>
      <label className="text-xs font-semibold text-gray-400 uppercase tracking-wide block">
        Kill Switch
      </label>
      <p className="text-xs text-gray-500 mt-0.5">
        {enabled ? 'Traffic blocked — all requests rejected' : 'Service running normally'}
      </p>
    </div>
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={() => onChange(!enabled)}
      disabled={disabled}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-40 ${
        enabled
          ? 'bg-rose-500 focus:ring-rose-400'
          : 'bg-gray-200 focus:ring-gray-300'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
          enabled ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  </div>
);

// ─── RollbackButton ──────────────────────────────────────────────────────────

const RollbackButton: React.FC<{
  onRollback: () => Promise<void>;
  onError: (msg: string) => void;
  disabled?: boolean;
  currentVersion?: string;
  previousVersion?: string;
}> = ({ onRollback, onError, disabled, currentVersion, previousVersion }) => {
  const [confirming, setConfirming] = useState(false);
  const [rolling, setRolling] = useState(false);

  const handleClick = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setRolling(true);
    setConfirming(false);
    try {
      await onRollback();
    } catch (err: any) {
      onError(err.message || 'Rollback failed');
    } finally {
      setRolling(false);
    }
  };

  return (
    <div className="flex items-center justify-between">
      <div>
        <label className="text-xs font-semibold text-gray-400 uppercase tracking-wide block">
          Rollback
        </label>
        {previousVersion && (
          <p className="text-xs text-gray-500 mt-0.5">Target: {previousVersion}</p>
        )}
      </div>
      <button
        onClick={handleClick}
        disabled={disabled || rolling}
        className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-40 ${
          confirming
            ? 'bg-rose-600 text-white hover:bg-rose-700'
            : 'border border-gray-200 text-gray-600 hover:bg-gray-50'
        }`}
      >
        {rolling ? 'Rolling back...' : confirming ? 'Confirm Rollback?' : 'Rollback'}
      </button>
    </div>
  );
};

// ─── RolloutPage ─────────────────────────────────────────────────────────────

const ENVIRONMENTS = ['production', 'staging', 'dev'];
const TENANT_ID = 'ops-console-default';

export const RolloutPage: React.FC = () => {
  const [environment, setEnvironment] = useState('production');
  const [canaryPercent, setCanaryPercent] = useState(0);
  const [killSwitch, setKillSwitch] = useState(false);
  const [currentVersion, setCurrentVersion] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isApplying, setIsApplying] = useState(false);

  useEffect(() => {
    loadConfig();
  }, [environment]);

  const loadConfig = async () => {
    setIsLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await mockConfigApiClient.getConfig(environment);
      setCanaryPercent(result.config.canary_percent);
      setKillSwitch(result.config.kill_switch);
      setCurrentVersion(result.version);
    } catch (err: any) {
      setError(err.message || 'Failed to load config');
    } finally {
      setIsLoading(false);
    }
  };

  const handleApply = async () => {
    setIsApplying(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await mockConfigApiClient.releaseConfig(
        environment,
        { canary_percent: canaryPercent, kill_switch: killSwitch },
        TENANT_ID,
      );
      setCurrentVersion(result.version);
      setSuccess(`Released → ${result.version}`);
      await loadConfig();
    } catch (err: any) {
      setError(err.message || 'Failed to apply config');
    } finally {
      setIsApplying(false);
    }
  };

  const handleRollback = async () => {
    setError(null);
    setSuccess(null);
    try {
      const result = await mockConfigApiClient.rollbackConfig(environment, TENANT_ID);
      setCurrentVersion(result.version);
      setSuccess(`Rolled back → ${result.version}`);
      await loadConfig();
    } catch (err: any) {
      setError(err.message || 'Rollback failed');
    }
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Ops</p>
          <h1 className="text-xl font-bold text-gray-900">Rollout Management</h1>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-400">Environment</label>
          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value)}
            className="px-2 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            {ENVIRONMENTS.map((env) => (
              <option key={env} value={env}>{env}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Status banner */}
      {isLoading && (
        <div className="mb-4 px-4 py-3 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-400 animate-pulse">
          Loading config...
        </div>
      )}
      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-700" role="alert">
          {success}
        </div>
      )}

      {/* Kill switch warning */}
      {killSwitch && (
        <div className="mb-4 px-4 py-3 bg-rose-50 border border-rose-300 rounded-lg text-sm font-medium text-rose-700 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
          Kill switch is ACTIVE — all traffic blocked
        </div>
      )}

      {/* Controls */}
      <div className="border border-gray-200 rounded-xl bg-white shadow-sm divide-y divide-gray-100">
        <div className="px-6 py-5">
          <CanarySlider
            value={canaryPercent}
            onChange={setCanaryPercent}
            disabled={isApplying || isLoading}
          />
        </div>

        <div className="px-6 py-5">
          <KillSwitchToggle
            enabled={killSwitch}
            onChange={setKillSwitch}
            disabled={isApplying || isLoading}
          />
        </div>

        <div className="px-6 py-5">
          <RollbackButton
            onRollback={handleRollback}
            onError={setError}
            disabled={isApplying || isLoading}
            currentVersion={currentVersion ?? undefined}
          />
        </div>
      </div>

      {/* Apply button */}
      <div className="mt-4 flex items-center justify-between">
        {currentVersion && (
          <span className="text-xs text-gray-400 font-mono">
            current: {currentVersion}
          </span>
        )}
        <button
          onClick={handleApply}
          disabled={isApplying || isLoading}
          className="ml-auto px-6 py-2.5 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 transition-colors"
        >
          {isApplying ? 'Applying...' : 'Apply Changes'}
        </button>
      </div>
    </div>
  );
};
