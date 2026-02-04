/**
 * 서명 감사 로그 컴포넌트
 * /reports/:id/sign 호출 이력 표시
 * 
 * @module SignHistory
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getSignHistory, SignHistory as SignHistoryType } from '../api/reports';

interface SignHistoryProps {
  reportId: string;
}

export const SignHistory: React.FC<SignHistoryProps> = ({ reportId }) => {
  const [history, setHistory] = useState<SignHistoryType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getSignHistory(reportId);
      setHistory(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sign history');
      console.error('Failed to load sign history:', err);
    } finally {
      setLoading(false);
    }
  }, [reportId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const formatDate = (timestamp: number): string => {
    return new Date(timestamp).toLocaleString();
  };

  const isExpired = (expiresAt: number): boolean => {
    return expiresAt < Date.now();
  };

  if (loading) {
    return (
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Sign History</h2>
        <div className="text-gray-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Sign History</h2>
        <div className="p-4 bg-red-100 border border-red-400 text-red-700 rounded text-sm">
          {error}
        </div>
      </div>
    );
  }

  if (!history || history.count === 0) {
    return (
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Sign History</h2>
        <div className="text-gray-500 text-sm">No sign history available</div>
      </div>
    );
  }

  return (
    <div className="bg-white shadow rounded-lg p-6 mb-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">Sign History</h2>
        <button
          onClick={loadHistory}
          className="text-sm text-indigo-600 hover:text-indigo-800"
        >
          Refresh
        </button>
      </div>
      
      <div className="text-sm text-gray-600 mb-4">
        Total: {history.count} sign request{history.count !== 1 ? 's' : ''}
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Requested By
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Issued At (iat)
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Expires At (exp)
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Token Preview
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {history.history.map((entry, index) => (
              <tr key={index} className="hover:bg-gray-50">
                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                  {entry.requestedBy}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                  {formatDate(entry.issuedAt)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                  {formatDate(entry.expiresAt)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  {isExpired(entry.expiresAt) ? (
                    <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-800 rounded">
                      Expired
                    </span>
                  ) : (
                    <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded">
                      Active
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-sm font-mono text-gray-500">
                  {entry.tokenPreview}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

