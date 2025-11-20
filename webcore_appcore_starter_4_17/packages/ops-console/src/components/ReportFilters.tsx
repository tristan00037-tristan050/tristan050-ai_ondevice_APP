/**
 * 리포트 필터 컴포넌트
 * severity, policy_version, 기간 프리셋 필터 지원
 * 
 * @module ReportFilters
 */

import React from 'react';

export type SeverityFilter = 'all' | 'info' | 'warn' | 'block';
export type DatePreset = 'all' | '24h' | '7d' | '30d';

export interface FilterState {
  id: string;
  severity: SeverityFilter;
  policyVersion: string;
  datePreset: DatePreset;
}

interface ReportFiltersProps {
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
}

export const ReportFilters: React.FC<ReportFiltersProps> = ({ filters, onFiltersChange }) => {
  const handleChange = (field: keyof FilterState, value: string) => {
    onFiltersChange({
      ...filters,
      [field]: value,
    });
  };

  return (
    <div className="bg-white shadow rounded-lg p-4 mb-6">
      <h3 className="text-lg font-semibold mb-4">Filters</h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* ID 필터 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Report ID
          </label>
          <input
            type="text"
            placeholder="Filter by ID..."
            value={filters.id}
            onChange={(e) => handleChange('id', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {/* Severity 필터 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Severity
          </label>
          <select
            value={filters.severity}
            onChange={(e) => handleChange('severity', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">All</option>
            <option value="info">Info</option>
            <option value="warn">Warn</option>
            <option value="block">Block</option>
          </select>
        </div>

        {/* Policy Version 필터 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Policy Version
          </label>
          <input
            type="text"
            placeholder="Filter by version..."
            value={filters.policyVersion}
            onChange={(e) => handleChange('policyVersion', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {/* 기간 프리셋 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Time Range
          </label>
          <select
            value={filters.datePreset}
            onChange={(e) => handleChange('datePreset', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">All Time</option>
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
        </div>
      </div>

      {/* 필터 초기화 버튼 */}
      {(filters.id || filters.severity !== 'all' || filters.policyVersion || filters.datePreset !== 'all') && (
        <div className="mt-4">
          <button
            onClick={() => onFiltersChange({
              id: '',
              severity: 'all',
              policyVersion: '',
              datePreset: 'all',
            })}
            className="text-sm text-indigo-600 hover:text-indigo-800"
          >
            Clear all filters
          </button>
        </div>
      )}
    </div>
  );
};

