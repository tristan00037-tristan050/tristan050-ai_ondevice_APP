/**
 * 리포트 상세 페이지
 * 서명/번들 다운로드 지원
 * 
 * @module ReportDetail
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getReport, signReport, getBundleDownloadUrl, Report } from '../api/reports';
import { SignHistory } from '../components/SignHistory';
import { BundleMeta } from '../components/BundleMeta';
import { useAuth } from '../hooks/useAuth';
import { invalidateCache } from '../api/client';

export const ReportDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { canDownload } = useAuth();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signing, setSigning] = useState(false);
  const [bundleUrl, setBundleUrl] = useState<string | null>(null);

  const loadReport = useCallback(async () => {
    if (!id) return;
    
    try {
      setLoading(true);
      setError(null);
      const data = await getReport(id);
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load report');
      console.error('Failed to load report:', err);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (id) {
      loadReport();
    }
  }, [id, loadReport]);


  const handleSignAndDownload = async () => {
    if (!id) return;
    
    try {
      setSigning(true);
      const signResponse = await signReport(id);
      const url = getBundleDownloadUrl(id, signResponse.token);
      setBundleUrl(url);
      
      // 번들 다운로드
      window.open(url, '_blank');
      
      // 캐시 무효화 및 리포트 재로드
      invalidateCache(`/reports/${id}`);
      invalidateCache(`/reports/${id}/sign-history`);
      await loadReport();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sign report');
      console.error('Failed to sign report:', err);
    } finally {
      setSigning(false);
    }
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

  if (error || !report) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          {error || 'Report not found'}
        </div>
        <button
          onClick={() => navigate('/reports')}
          className="mt-4 px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
        >
          Back to Reports
        </button>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6 flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Report Details</h1>
        <button
          onClick={() => navigate('/reports')}
          className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
        >
          Back
        </button>
      </div>

      {/* 리포트 정보 */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Report Information</h2>
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm font-medium text-gray-500">ID</dt>
            <dd className="mt-1 text-sm text-gray-900 font-mono">{report.id}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Tenant ID</dt>
            <dd className="mt-1 text-sm text-gray-900">{report.tenantId}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Created At</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {new Date(report.createdAt).toLocaleString()}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Updated At</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {new Date(report.updatedAt).toLocaleString()}
            </dd>
          </div>
        </dl>
      </div>

      {/* 리포트 데이터 */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Report Data</h2>
        <pre className="bg-gray-50 p-4 rounded overflow-x-auto text-sm">
          {JSON.stringify(report.report, null, 2)}
        </pre>
      </div>

      {/* 마크다운 (있는 경우) */}
      {report.markdown && (
        <div className="bg-white shadow rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Markdown</h2>
          <div className="prose max-w-none">
            <pre className="whitespace-pre-wrap">{report.markdown}</pre>
          </div>
        </div>
      )}

      {/* 액션 버튼 */}
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Actions</h2>
        {!canDownload && (
          <div className="mb-4 p-3 bg-yellow-100 border border-yellow-400 text-yellow-700 rounded text-sm">
            <strong>Read-only mode:</strong> Download actions are disabled. Switch to "Download" permission to enable.
          </div>
        )}
        <div className="flex space-x-4">
          <button
            onClick={handleSignAndDownload}
            disabled={signing || !canDownload}
            className="px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title={!canDownload ? 'Download permission required' : ''}
          >
            {signing ? 'Signing...' : 'Sign & Download Bundle'}
          </button>
          {bundleUrl && canDownload && (
            <a
              href={bundleUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
            >
              Download Bundle
            </a>
          )}
        </div>
      </div>

      {/* 번들 크기/구성 카드 */}
      {id && <BundleMeta reportId={id} />}

      {/* 서명 감사 로그 */}
      {id && <SignHistory reportId={id} />}
    </div>
  );
};

