/**
 * 타임라인 페이지
 * 24/48/72/168h 지원
 * 
 * @module Timeline
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getTimeline, Timeline, TimelineBucket } from '../api/reports';

const WINDOW_OPTIONS = [
  { value: 24, label: '24 hours' },
  { value: 48, label: '48 hours' },
  { value: 72, label: '72 hours' },
  { value: 168, label: '168 hours (7 days)' },
];

export const TimelinePage: React.FC = () => {
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [windowH, setWindowH] = useState(24);

  const loadTimeline = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getTimeline(windowH);
      setTimeline(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load timeline');
      console.error('Failed to load timeline:', err);
    } finally {
      setLoading(false);
    }
  }, [windowH]);

  useEffect(() => {
    loadTimeline();
    
    // 주기적 폴링 (60초)
    const interval = setInterval(() => {
      loadTimeline();
    }, 60000);
    
    return () => clearInterval(interval);
  }, [windowH, loadTimeline]);

  const formatTime = (timestamp: number): string => {
    return new Date(timestamp).toLocaleString();
  };

  const getMaxCount = (buckets: TimelineBucket[]): number => {
    if (buckets.length === 0) return 1;
    return Math.max(
      ...buckets.map(b => Math.max(b.info, b.warn, b.block)),
      1
    );
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex justify-center items-center py-8">
          <div className="text-gray-500">Loading...</div>
        </div>
      </div>
    );
  }

  if (error || !timeline) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          {error || 'Failed to load timeline'}
        </div>
      </div>
    );
  }

  const maxCount = getMaxCount(timeline.buckets);

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6 flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Timeline</h1>
        <select
          value={windowH}
          onChange={(e) => setWindowH(parseInt(e.target.value))}
          className="px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {WINDOW_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* 통계 요약 */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Summary</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">
              {timeline.buckets.reduce((sum, b) => sum + b.info, 0)}
            </div>
            <div className="text-sm text-gray-600">INFO</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-yellow-600">
              {timeline.buckets.reduce((sum, b) => sum + b.warn, 0)}
            </div>
            <div className="text-sm text-gray-600">WARN</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-600">
              {timeline.buckets.reduce((sum, b) => sum + b.block, 0)}
            </div>
            <div className="text-sm text-gray-600">BLOCK</div>
          </div>
        </div>
      </div>

      {/* 타임라인 테이블 */}
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Time
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                INFO
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                WARN
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                BLOCK
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Chart
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {timeline.buckets.map((bucket, index) => (
              <tr key={index} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {formatTime(bucket.time)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {bucket.info}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {bucket.warn}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {bucket.block}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center space-x-1">
                    <div
                      className="bg-blue-500 h-4 rounded"
                      style={{ width: `${(bucket.info / maxCount) * 100}%` }}
                      title={`INFO: ${bucket.info}`}
                    />
                    <div
                      className="bg-yellow-500 h-4 rounded"
                      style={{ width: `${(bucket.warn / maxCount) * 100}%` }}
                      title={`WARN: ${bucket.warn}`}
                    />
                    <div
                      className="bg-red-500 h-4 rounded"
                      style={{ width: `${(bucket.block / maxCount) * 100}%` }}
                      title={`BLOCK: ${bucket.block}`}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

