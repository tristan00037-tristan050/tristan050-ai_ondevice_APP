/**
 * Kill Switch Toggle Component
 * Enable/disable feature via kill switch
 */

import React from 'react';

interface KillSwitchToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}

export const KillSwitchToggle: React.FC<KillSwitchToggleProps> = ({
  enabled,
  onChange,
  disabled = false,
}) => {
  return (
    <div className="kill-switch-toggle">
      <label htmlFor="kill-switch">
        Kill Switch: {enabled ? 'ON (Feature Disabled)' : 'OFF (Feature Enabled)'}
      </label>
      <input
        id="kill-switch"
        type="checkbox"
        checked={enabled}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="toggle"
      />
    </div>
  );
};

