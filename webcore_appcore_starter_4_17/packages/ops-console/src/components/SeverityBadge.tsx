/**
 * Severity 뱃지 컴포넌트
 * 
 * @module SeverityBadge
 */

import React from 'react';

export type Severity = 'info' | 'warn' | 'block';

interface SeverityBadgeProps {
  severity: Severity;
  className?: string;
}

const severityColors: Record<Severity, string> = {
  info: 'bg-blue-100 text-blue-800',
  warn: 'bg-yellow-100 text-yellow-800',
  block: 'bg-red-100 text-red-800',
};

const severityLabels: Record<Severity, string> = {
  info: 'INFO',
  warn: 'WARN',
  block: 'BLOCK',
};

export const SeverityBadge: React.FC<SeverityBadgeProps> = ({ severity, className = '' }) => {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${severityColors[severity]} ${className}`}
    >
      {severityLabels[severity]}
    </span>
  );
};

