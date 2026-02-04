/**
 * 번들 크기/구성 카드 컴포넌트
 * bundle_meta.json 정보 표시
 * 
 * @module BundleMeta
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getBundleMeta, BundleMeta as BundleMetaType } from '../api/reports';

interface BundleMetaProps {
  reportId: string;
}

export const BundleMeta: React.FC<BundleMetaProps> = ({ reportId }) => {
  const [meta, setMeta] = useState<BundleMetaType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMeta = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getBundleMeta(reportId);
      setMeta(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load bundle meta');
      console.error('Failed to load bundle meta:', err);
    } finally {
      setLoading(false);
    }
  }, [reportId]);

  useEffect(() => {
    loadMeta();
  }, [loadMeta]);

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  };

  const formatChecksum = (checksum: string): string => {
    return `${checksum.substring(0, 8)}...${checksum.substring(checksum.length - 8)}`;
  };

  if (loading) {
    return (
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Bundle Information</h2>
        <div className="text-gray-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Bundle Information</h2>
        <div className="p-4 bg-red-100 border border-red-400 text-red-700 rounded text-sm">
          {error}
        </div>
      </div>
    );
  }

  if (!meta) {
    return null;
  }

  return (
    <div className="bg-white shadow rounded-lg p-6 mb-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">Bundle Information</h2>
        <button
          onClick={loadMeta}
          className="text-sm text-indigo-600 hover:text-indigo-800"
        >
          Refresh
        </button>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 mb-6">
        <div className="bg-gray-50 rounded-lg p-4">
          <div className="text-sm font-medium text-gray-500 mb-1">Total Files</div>
          <div className="text-2xl font-bold text-gray-900">{meta.totalFiles}</div>
        </div>
        <div className="bg-gray-50 rounded-lg p-4">
          <div className="text-sm font-medium text-gray-500 mb-1">Total Size</div>
          <div className="text-2xl font-bold text-gray-900">{formatBytes(meta.totalSize)}</div>
        </div>
        <div className="bg-gray-50 rounded-lg p-4">
          <div className="text-sm font-medium text-gray-500 mb-1">Estimated ZIP Size</div>
          <div className="text-2xl font-bold text-gray-900">{formatBytes(meta.estimatedZipSize)}</div>
        </div>
      </div>

      {/* 파일 목록 */}
      <div className="mb-4">
        <h3 className="text-lg font-semibold mb-3">Files</h3>
        <div className="space-y-2">
          {meta.files.map((file, index) => (
            <div
              key={index}
              className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
            >
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-900">{file.name}</div>
                <div className="text-xs text-gray-500 mt-1">
                  {formatBytes(file.size)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs font-mono text-gray-600">
                  {formatChecksum(file.checksum)}
                </div>
                <div className="text-xs text-gray-500 mt-1">SHA256</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 체크섬 상세 */}
      <div>
        <h3 className="text-lg font-semibold mb-3">Checksums</h3>
        <div className="bg-gray-50 rounded-lg p-4">
          <pre className="text-xs font-mono text-gray-700 overflow-x-auto">
            {JSON.stringify(meta.checksums, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
};

