/**
 * 리포트 목록 페이지
 * 필터/페이지네이션 지원
 * 
 * @module Reports
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getReports, ReportSummary, GetReportsParams } from '../api/reports';
import { ReportsTable } from '../components/ReportsTable';
import { ReportFilters, FilterState } from '../components/ReportFilters';
import { BlockAlert } from '../components/BlockAlert';
import { invalidateCache } from '../api/client';

const ITEMS_PER_PAGE = 20;

export const Reports: React.FC = () => {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [filters, setFilters] = useState<FilterState>({
    id: '',
    severity: 'all',
    policyVersion: '',
    datePreset: 'all',
  });

  // 서버 측 필터링을 위한 파라미터 생성
  const buildApiParams = useCallback((pageNum: number): GetReportsParams => {
    const params: GetReportsParams = {
      page: pageNum,
      limit: ITEMS_PER_PAGE,
    };

    // severity 필터
    if (filters.severity !== 'all') {
      params.severity = filters.severity;
    }

    // policy_version 필터
    if (filters.policyVersion) {
      params.policy_version = filters.policyVersion;
    }

    // 기간 프리셋 필터 (since로 변환)
    if (filters.datePreset !== 'all') {
      const now = Date.now();
      let cutoffTime = 0;
      switch (filters.datePreset) {
        case '24h':
          cutoffTime = now - 24 * 3600000;
          break;
        case '7d':
          cutoffTime = now - 7 * 24 * 3600000;
          break;
        case '30d':
          cutoffTime = now - 30 * 24 * 3600000;
          break;
      }
      params.since = cutoffTime;
    }

    return params;
  }, [filters]);

  // 리포트 로드 (서버 측 필터링)
  const loadReports = useCallback(async (pageNum: number = currentPage) => {
    try {
      setLoading(true);
      setError(null);
      
      const apiParams = buildApiParams(pageNum);
      const response = await getReports(apiParams);
      
      // ID 필터는 클라이언트 측에서만 적용 (서버 측 필터링에 포함되지 않음)
      let filtered = response.reports;
      if (filters.id) {
        filtered = filtered.filter(r => 
          r.id.toLowerCase().includes(filters.id.toLowerCase())
        );
      }
      
      setReports(filtered);
      setTotalCount(response.pagination.totalCount);
      setTotalPages(response.pagination.totalPages);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load reports');
      console.error('Failed to load reports:', err);
    } finally {
      setLoading(false);
    }
  }, [buildApiParams, currentPage, filters.id]);

  // 필터 변경 시 첫 페이지로 리셋하고 재로드
  useEffect(() => {
    setCurrentPage(1);
    loadReports(1);
  }, [filters.severity, filters.policyVersion, filters.datePreset, loadReports]);

  // 페이지 변경 시 재로드
  useEffect(() => {
    loadReports(currentPage);
  }, [currentPage, loadReports]);

  // 주기적 폴링 (30초) - 현재 필터 유지
  useEffect(() => {
    const interval = setInterval(() => {
      loadReports(currentPage);
    }, 30000);
    
    return () => clearInterval(interval);
  }, [loadReports, currentPage]);

  const handleRefresh = () => {
    invalidateCache('/reports');
    loadReports(currentPage);
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6 flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Reports</h1>
        <button
          onClick={handleRefresh}
          className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
        >
          Refresh
        </button>
      </div>

      {/* BLOCK 급증 알림 */}
      <BlockAlert threshold={10} deltaPercent={50} />

      {/* 필터 컴포넌트 */}
      <ReportFilters filters={filters} onFiltersChange={setFilters} />

      {/* 에러 메시지 */}
      {error && (
        <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      {/* 리포트 테이블 */}
      <ReportsTable reports={reports} loading={loading} />

      {/* 페이지네이션 */}
      {totalPages > 1 && (
        <div className="mt-6 flex justify-center items-center space-x-2">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="px-4 py-2 border border-gray-300 rounded-md disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm text-gray-600">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="px-4 py-2 border border-gray-300 rounded-md disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}

      {/* 통계 */}
      <div className="mt-6 text-sm text-gray-600">
        Showing {reports.length} of {totalCount} reports
        {reports.length < totalCount && (
          <span className="ml-2 text-indigo-600">
            (서버 측 필터링 적용)
          </span>
        )}
      </div>
    </div>
  );
};

