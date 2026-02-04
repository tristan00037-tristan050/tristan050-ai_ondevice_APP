/**
 * Canary Slider Component
 * Adjust canary percentage (0-100)
 */

import React from 'react';

interface CanarySliderProps {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}

export const CanarySlider: React.FC<CanarySliderProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  return (
    <div className="canary-slider">
      <label htmlFor="canary-percent">
        Canary Percentage: {value}%
      </label>
      <input
        id="canary-percent"
        type="range"
        min="0"
        max="100"
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
        disabled={disabled}
        className="slider"
      />
      <div className="slider-labels">
        <span>0%</span>
        <span>100%</span>
      </div>
    </div>
  );
};

