/**
 * Rollback Button Component
 * Rollback to previous config version
 */

import React, { useState } from 'react';

interface RollbackButtonProps {
  onRollback: () => Promise<void>;
  disabled?: boolean;
  currentVersion?: string;
  previousVersion?: string;
}

export const RollbackButton: React.FC<RollbackButtonProps> = ({
  onRollback,
  disabled = false,
  currentVersion,
  previousVersion,
}) => {
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRollback = async () => {
    if (!confirm('Are you sure you want to rollback to the previous version?')) {
      return;
    }

    setIsRollingBack(true);
    setError(null);

    try {
      await onRollback();
    } catch (err: any) {
      setError(err.reason_code || err.message || 'Rollback failed');
    } finally {
      setIsRollingBack(false);
    }
  };

  return (
    <div className="rollback-button">
      <button
        onClick={handleRollback}
        disabled={disabled || isRollingBack || !previousVersion}
        className="btn-rollback"
      >
        {isRollingBack ? 'Rolling back...' : 'Rollback'}
      </button>
      {currentVersion && (
        <div className="version-info">
          Current: {currentVersion}
          {previousVersion && ` → Previous: ${previousVersion}`}
        </div>
      )}
      {error && (
        <div className="error" role="alert">
          Error: {error}
        </div>
      )}
    </div>
  );
};

