/**
 * BLOCK 급증 알림 컴포넌트
 * 최근 24h BLOCK 급증 감지 및 알림 표시
 * 
 * @module BlockAlert
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getTimeline } from '../api/reports';

interface BlockAlertProps {
  threshold?: number; // 임계값 (기본: 10)
  deltaPercent?: number; // 급증 비율 (기본: 50%)
}

export const BlockAlert: React.FC<BlockAlertProps> = ({
  threshold = 10,
  deltaPercent = 50,
}) => {
  const [alert, setAlert] = useState<{
    current: number;
    previous: number;
    delta: number;
    deltaPercent: number;
    severity: 'info' | 'warning' | 'critical';
  } | null>(null);
  const [loading, setLoading] = useState(true);

  const checkBlockSpike = useCallback(async () => {
    try {
      setLoading(true);
      
      // 최근 24h와 이전 24h 타임라인 조회
      const [current24h, previous24h] = await Promise.all([
        getTimeline(24),
        // 이전 24h는 현재 시간 기준으로 계산
        // 실제로는 별도 API가 필요하거나, 현재 타임라인에서 이전 버킷 사용
        getTimeline(48).then(timeline => {
          // 48h 타임라인에서 첫 24h는 이전, 나머지는 현재
          const buckets = timeline.buckets;
          const midPoint = Math.floor(buckets.length / 2);
          return {
            ...timeline,
            buckets: buckets.slice(0, midPoint),
          };
        }),
      ]);

      // BLOCK 카운트 집계
      const currentBlock = current24h.buckets.reduce((sum, b) => sum + b.block, 0);
      const previousBlock = previous24h.buckets.reduce((sum, b) => sum + b.block, 0);

      // 급증 감지
      if (currentBlock >= threshold && previousBlock > 0) {
        const delta = currentBlock - previousBlock;
        const deltaPct = ((delta / previousBlock) * 100);
        
        if (deltaPct >= deltaPercent) {
          // 심각도 결정
          let severity: 'info' | 'warning' | 'critical' = 'info';
          if (deltaPct >= 200) {
            severity = 'critical';
          } else if (deltaPct >= 100) {
            severity = 'warning';
          }

          setAlert({
            current: currentBlock,
            previous: previousBlock,
            delta,
            deltaPercent: deltaPct,
            severity,
          });
        } else {
          setAlert(null);
        }
      } else {
        setAlert(null);
      }
    } catch (err) {
      console.error('Failed to check block spike:', err);
      setAlert(null);
    } finally {
      setLoading(false);
    }
  }, [threshold, deltaPercent]);

  useEffect(() => {
    checkBlockSpike();
    // 주기적 체크 (5분)
    const interval = setInterval(() => {
      checkBlockSpike();
    }, 300000);
    
    return () => clearInterval(interval);
  }, [checkBlockSpike]);

  if (loading || !alert) {
    return null;
  }

  const bgColor = {
    info: 'bg-blue-100 border-blue-400 text-blue-700',
    warning: 'bg-yellow-100 border-yellow-400 text-yellow-700',
    critical: 'bg-red-100 border-red-400 text-red-700',
  }[alert.severity];

  const icon = {
    info: 'ℹ️',
    warning: '⚠️',
    critical: '🚨',
  }[alert.severity];

  return (
    <div className={`mb-4 p-4 border rounded-lg ${bgColor}`}>
      <div className="flex items-start">
        <div className="text-2xl mr-3">{icon}</div>
        <div className="flex-1">
          <div className="font-semibold mb-1">
            BLOCK Severity Spike Detected
          </div>
          <div className="text-sm">
            <div>
              Current 24h: <strong>{alert.current}</strong> BLOCK events
            </div>
            <div>
              Previous 24h: <strong>{alert.previous}</strong> BLOCK events
            </div>
            <div>
              Increase: <strong>+{alert.delta}</strong> ({alert.deltaPercent.toFixed(1)}%)
            </div>
            <div className="mt-2 text-xs opacity-75">
              Threshold: {threshold} events, Delta: {deltaPercent}%
            </div>
          </div>
        </div>
        <button
          onClick={() => setAlert(null)}
          className="text-gray-500 hover:text-gray-700"
        >
          ✕
        </button>
      </div>
    </div>
  );
};

