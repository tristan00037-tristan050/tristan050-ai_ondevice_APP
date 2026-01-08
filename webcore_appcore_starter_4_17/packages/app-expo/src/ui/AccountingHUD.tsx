/**
 * HUD 화면 (최소 동작형) — 승인/Export/대사 + 오프라인 큐 연동
 * 
 * @module app-expo/ui/AccountingHUD
 */

import React, { useEffect, useState } from 'react';
// @ts-ignore - React Native types
import { View, Text, Button, TextInput, ScrollView, TouchableOpacity } from 'react-native';
import { useScreenPrivacy } from './hooks/useScreenPrivacy';
import { useOnline } from './hooks/useOnline';
import { useOfflineQueue } from './hooks/useOfflineQueue';
import { enqueue, flushQueue, startQueueAutoFlush } from './offline/offline-queue';
import QueueBadge from './components/QueueBadge';
import ManualReviewButton from './components/ManualReviewButton';
import QueueInspector from './components/QueueInspector';
import WhyBlockCard from './components/WhyBlockCard';
import { checkLeakageBatch, extractLeakageAudit } from '../shared/leak_guard';
import {
  postSuggest,
  postApproval,
  postExport,
  postReconCreate,
  postReconMatch,
  type ClientCfg,
  type ApiError,
  isMock,
  getSuggestEngine as getOldSuggestEngine,
} from '../hud/accounting-api';
import { suggestWithEngine, getSuggestEngine } from '../hud/engines/index';
import { saveEncryptedReport, loadEncryptedReport } from '../security/secure-storage';

type Props = { cfg: ClientCfg };

export default function AccountingHUD({ cfg }: Props) {
  useScreenPrivacy();
  const online = useOnline();
  const { count, lastSyncTs } = useOfflineQueue();
  const [reportId, setReportId] = useState('demo-report-1');
  const [desc, setDesc] = useState('커피 영수증 4500원');
  const [suggestOut, setSuggestOut] = useState<any>(null);
  const [suggestOutBlocked, setSuggestOutBlocked] = useState<{ blocked: boolean; reason_code?: string } | null>(null);
  const [selectedPostingIndex, setSelectedPostingIndex] = useState<number>(0); // 선택된 posting index (0부터 시작)
  const [sessionId, setSessionId] = useState<string>('');
  const [exportJob, setExportJob] = useState<any>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<string | null>(null);
  const [showErrorDetails, setShowErrorDetails] = useState<boolean>(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [bffConfigError, setBffConfigError] = useState<string | null>(null);
  
  // 수동 검토 요청 카운트 (Mock: localStorage, Live: 나중에 BFF 연동)
  const [manualReviewCount, setManualReviewCount] = useState<number>(0);
  const [lastManualReviewTime, setLastManualReviewTime] = useState<string | null>(null);
  const [queueInspectorVisible, setQueueInspectorVisible] = useState<boolean>(false);
  const [queueFullError, setQueueFullError] = useState<boolean>(false);
  
  // 엔진 관련 상태 (R8-S2)
  const [engineMeta, setEngineMeta] = useState<{ label: string; type: string } | null>(null);
  const [engineLoading, setEngineLoading] = useState(false);
  const [engineError, setEngineError] = useState<string | null>(null);
  
  // 공통 에러 핸들러
  function handleApiError(error: ApiError, context: string) {
    console.error(`[${context} Error]`, error);
    setErrorMessage(error.message || `${context} 실패`);
    setErrorDetails(error.details || error.message || '자세한 내용은 콘솔 로그를 참조하세요.');
    setShowErrorDetails(false);
  }
  
  // BFF 설정 검증
  useEffect(() => {
    if (isMock(cfg)) {
      setBffConfigError(null);
      return;
    }
    
    const errors: string[] = [];
    if (!cfg.baseUrl || cfg.baseUrl === '') {
      errors.push('BFF URL이 설정되지 않았습니다');
    }
    if (!cfg.tenantId || cfg.tenantId === '') {
      errors.push('Tenant ID가 설정되지 않았습니다');
    }
    if (!cfg.apiKey || cfg.apiKey === '') {
      errors.push('API Key가 설정되지 않았습니다');
    }
    
    if (errors.length > 0) {
      setBffConfigError(errors.join(', '));
    } else {
      // BFF 연결 테스트
      fetch(`${cfg.baseUrl}/healthz`, { method: 'GET' })
        .then(res => {
          if (res.status === 401 || res.status === 403) {
            setBffConfigError('권한 또는 API 키 문제입니다. 관리자에게 문의해 주세요.');
          } else if (res.status === 404) {
            setBffConfigError('요청한 리소스를 찾을 수 없습니다. (URL/경로 확인 필요)');
          } else if (res.status >= 500) {
            setBffConfigError('서버 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
          } else if (!res.ok) {
            setBffConfigError(`BFF에 연결할 수 없습니다 (HTTP ${res.status})`);
          } else {
            setBffConfigError(null);
          }
        })
        .catch(() => {
          setBffConfigError('BFF에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.');
        });
    }
  }, [cfg]);
  
  useEffect(() => {
    startQueueAutoFlush(cfg);
  }, [cfg]);
  
  // 엔진 초기화 (R8-S2)
  useEffect(() => {
    let cancelled = false;
    
    async function initEngine() {
      try {
        setEngineLoading(true);
        setEngineError(null);
        
        const engine = getSuggestEngine(cfg);
        setEngineMeta({
          label: engine.meta.label,
          type: engine.meta.type,
        });
        
        // 엔진이 초기화 메서드를 가지고 있으면 호출
        if (engine.initialize && !engine.isReady) {
          await engine.initialize();
        }
        
        if (!cancelled) {
          setEngineLoading(false);
          setEngineMeta({
            label: engine.meta.label,
            type: engine.meta.type,
          });
        }
      } catch (error: any) {
        if (!cancelled) {
          console.error('[AccountingHUD] Engine initialization failed:', error);
          setEngineError(error.message || 'Engine initialization failed');
          setEngineLoading(false);
        }
      }
    }
    
    initEngine();
    
    return () => {
      cancelled = true;
    };
  }, [cfg]);
  
  // localStorage에서 수동 검토 카운트 로드 (Mock 모드용)
  useEffect(() => {
    if (isMock(cfg)) {
      try {
        if (typeof window !== 'undefined' && window.localStorage) {
          const stored = localStorage.getItem('manual_review_count');
          const lastTime = localStorage.getItem('manual_review_last_time');
          if (stored) {
            setManualReviewCount(parseInt(stored, 10));
          }
          if (lastTime) {
            setLastManualReviewTime(lastTime);
          }
        }
      } catch (e) {
        // localStorage 사용 불가 시 무시
      }
    }
  }, [cfg]);
  
  const handleManualReviewSuccess = () => {
    setSuccessMessage('수동 검토 큐에 추가되었습니다.');
    setTimeout(() => setSuccessMessage(null), 3000);
    
    // 카운트 증가
    const newCount = manualReviewCount + 1;
    setManualReviewCount(newCount);
    const now = new Date().toISOString();
    setLastManualReviewTime(now);
    
    // Mock 모드: localStorage에 저장
    if (isMock(cfg)) {
      try {
        if (typeof window !== 'undefined' && window.localStorage) {
          localStorage.setItem('manual_review_count', String(newCount));
          localStorage.setItem('manual_review_last_time', now);
        }
      } catch (e) {
        // localStorage 사용 불가 시 무시
      }
    }
  };

  async function onSuggest() {
    setErrorMessage(null);
    setErrorDetails(null);
    
    // R8-S1: 새로운 SuggestEngine 계층 사용
    try {
      const ctx = {
        domain: 'accounting' as const,
        tenantId: cfg.tenantId || 'default',
        userId: 'hud-user-1',
      };
      
      const input = {
        text: desc,
        meta: {
          amount: 4500,
          currency: 'KRW',
        },
      };
      
      const result = await suggestWithEngine(cfg, ctx, input);
      
      // 기존 응답 형식으로 변환
      const convertedItems = result.items.map((item) => {
        const payload = item.payload as any;
        return {
          id: item.id,
          account: payload?.account,
          amount: payload?.amount || 4500,
          currency: payload?.currency || 'KRW',
          vendor: payload?.vendor,
          description: item.title || payload?.description || desc,
          rationale: item.description || payload?.rationale,
          score: item.score || 0.5,
          risk: payload?.risk || { level: 'LOW' as const, reasons: [], score: 0 },
        };
      });
      
      const out = { items: convertedItems, confidence: result.confidence };
      
      // Leakage Firewall v1: 출력 렌더 직전 검사
      const leakResult = checkLeakageBatch(desc, out.items || []);
      if (!leakResult.pass) {
        // 감사 로그 (meta-only)
        const audit = extractLeakageAudit(leakResult);
        console.warn('[Leakage Firewall] Blocked:', audit);
        
        setSuggestOutBlocked({
          blocked: true,
          reason_code: leakResult.reason_code,
        });
        setSuggestOut(null); // 출력 표시 차단
        return;
      }
      
      setSuggestOutBlocked({ blocked: false });
      setSuggestOut(out);
      await saveEncryptedReport(reportId, out);
    } catch (e: any) {
      // 네트워크 오류는 기존 postSuggest로 폴백 (오프라인 큐 지원)
      if (e.kind === 'network' || (e.message && e.message.includes('network'))) {
        const body = { items: [{ desc, amount: '4500', currency: 'KRW' }] };
        try {
          await enqueue({ kind: 'suggest', body, idem: `idem_suggest_${Date.now()}` });
        } catch (queueError: any) {
          if (queueError.message === 'QUEUE_FULL') {
            setQueueFullError(true);
            setErrorMessage('오프라인 큐가 가득 찼습니다. 네트워크 복구 후 다시 시도해 주세요.');
          } else {
            handleApiError(queueError, 'Queue');
          }
        }
      } else {
        // 클라이언트/서버 오류는 사용자에게 표시
        handleApiError(e, 'Suggest');
      }
    }
  }

  async function onApprove() {
    const selectedIndex = selectedPostingIndex;
    const selectedPosting = suggestOut?.items?.[selectedIndex] || suggestOut?.postings?.[selectedIndex];
    const id = selectedPosting?.id ?? suggestOut?.items?.[0]?.id ?? suggestOut?.postings?.[0]?.id ?? 'sample-id';
    const idem = `idem_approve_${Date.now()}`;
    
    // 선택 정보 계산
    const top1_selected = selectedIndex === 0;
    const selected_rank = selectedIndex + 1; // 1부터 시작
    const ai_score = suggestOut?.confidence ?? undefined; // 전체 confidence를 사용 (개별 posting score가 없을 경우)
    
    const approvalOpts = {
      idem,
      top1_selected,
      selected_rank,
      ...(ai_score !== undefined && { ai_score }),
    };
    
    setErrorMessage(null);
    setErrorDetails(null);
    try {
      await postApproval(cfg, id, 'approve', 'OK', approvalOpts);
    } catch (e: any) {
      if (e.kind === 'network') {
        try {
          await enqueue({ 
            kind: 'approval', 
            id, 
            action: 'approve', 
            note: 'OK', 
            idem,
            top1_selected,
            selected_rank,
            ...(ai_score !== undefined && { ai_score }),
          });
        } catch (queueError: any) {
          if (queueError.message === 'QUEUE_FULL') {
            setQueueFullError(true);
            setErrorMessage('오프라인 큐가 가득 찼습니다. 네트워크 복구 후 다시 시도해 주세요.');
          } else {
            handleApiError(queueError, 'Queue');
          }
        }
      } else {
        handleApiError(e, 'Approval');
      }
    }
  }

  async function onExport() {
    setErrorMessage(null);
    setErrorDetails(null);
    
    // Leakage Firewall v1: Export 차단 (Fail-Closed)
    if (suggestOutBlocked?.blocked) {
      const error: ApiError = {
        kind: 'client',
        status: 400,
        message: 'Leakage Firewall: 차단된 출력은 Export할 수 없습니다',
        details: JSON.stringify({ reason_code: suggestOutBlocked.reason_code }),
      };
      handleApiError(error, 'Export');
      return;
    }
    
    const idem = `idem_export_${Date.now()}`;
    try {
      const out = await postExport(
        cfg,
        { since: new Date(Date.now() - 7 * 86400000).toISOString(), limitDays: 7 },
        { idem }
      );
      setExportJob(out);
    } catch (e: any) {
      if (e.kind === 'network') {
        try {
          await enqueue({
            kind: 'export',
            body: { since: new Date(Date.now() - 7 * 86400000).toISOString(), limitDays: 7 },
            idem,
          });
        } catch (queueError: any) {
          if (queueError.message === 'QUEUE_FULL') {
            setQueueFullError(true);
            setErrorMessage('오프라인 큐가 가득 찼습니다. 네트워크 복구 후 다시 시도해 주세요.');
          } else {
            handleApiError(queueError, 'Queue');
          }
        }
      } else {
        handleApiError(e, 'Export');
      }
    }
  }

  async function onReconCreate() {
    setErrorMessage(null);
    setErrorDetails(null);
    const idem = `idem_recon_${Date.now()}`;
    const body = {
      bank: [{ id: 'b1', amount: '4500', date: new Date().toISOString(), currency: 'KRW' }],
      ledger: [{ id: 'l1', amount: '4500', date: new Date().toISOString(), currency: 'KRW', account: '8000' }],
    };
    try {
      const out = await postReconCreate(cfg, body, { idem });
      setSessionId(out.sessionId ?? out.id ?? '');
    } catch (e: any) {
      if (e.kind === 'network') {
        try {
          await enqueue({ kind: 'recon_create', body, idem });
        } catch (queueError: any) {
          if (queueError.message === 'QUEUE_FULL') {
            setQueueFullError(true);
            setErrorMessage('오프라인 큐가 가득 찼습니다. 네트워크 복구 후 다시 시도해 주세요.');
          } else {
            handleApiError(queueError, 'Queue');
          }
        }
      } else {
        handleApiError(e, 'Recon Create');
      }
    }
  }

  async function onReconMatch() {
    if (!sessionId) {
      return;
    }
    const idem = `idem_match_${Date.now()}`;
    try {
      await postReconMatch(cfg, sessionId, 'b1', 'l1', { idem });
    } catch (e: any) {
      if (e.kind === 'network') {
        try {
          await enqueue({ kind: 'recon_match', sessionId, bank_id: 'b1', ledger_id: 'l1', idem });
        } catch (queueError: any) {
          if (queueError.message === 'QUEUE_FULL') {
            setQueueFullError(true);
            setErrorMessage('오프라인 큐가 가득 찼습니다. 네트워크 복구 후 다시 시도해 주세요.');
          } else {
            handleApiError(queueError, 'Queue');
          }
        }
      } else {
        handleApiError(e, 'Recon Match');
      }
    }
  }

  async function onLoadLocal() {
    const data = await loadEncryptedReport(reportId);
    
    // Leakage Firewall v1: 출력 렌더 직전 검사
    const leakResult = checkLeakageBatch(desc, data?.items || []);
    if (!leakResult.pass) {
      // 감사 로그 (meta-only)
      const audit = extractLeakageAudit(leakResult);
      console.warn('[Leakage Firewall] Blocked:', audit);
      
      setSuggestOutBlocked({
        blocked: true,
        reason_code: leakResult.reason_code,
      });
      setSuggestOut(null); // 출력 표시 차단
      return;
    }
    
    setSuggestOutBlocked({ blocked: false });
    setSuggestOut(data);
  }

  // ScreenPrivacyGate 일시적으로 제거 (웹에서 expo-blur 문제 가능성)
  const mode = isMock(cfg) ? 'Mock' : 'Live(BFF)';
  const networkStatus = online === null ? '...' : online ? 'Online' : 'Offline';
  const networkIcon = online === null ? '🟡' : online ? '🟢' : '🔴';
  
  // Suggest 엔진 정보 (새로운 SuggestEngine 계층 사용)
  // 엔진 메타 정보는 useEffect에서 초기화된 값을 사용
  const engineLabel = engineLoading
    ? 'Loading...'
    : engineError
    ? 'Error'
    : engineMeta?.label ?? 'Rule';
  
  return (
    // @ts-ignore - React Native JSX
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
        {/* 상단 상태바 */}
        {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
        <View style={{ 
          backgroundColor: isMock(cfg) ? '#f0f0f0' : '#e3f2fd', 
          padding: 12, 
          borderRadius: 4, 
          borderWidth: 1, 
          borderColor: isMock(cfg) ? '#ccc' : '#90caf9',
          flexDirection: 'row',
          alignItems: 'center',
          gap: 12,
        }}>
          {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
          <Text style={{ fontSize: 14, fontWeight: 'bold' }}>
            {networkIcon} {networkStatus} · {mode} · Queue: {count}
          </Text>
          {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
          <Text style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
            Engine: {engineLabel}
            {engineError && ' ⚠️'}
          </Text>
          {/* 큐 인스펙터 버튼 */}
          {count > 0 && (
            // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
            <TouchableOpacity 
              onPress={() => setQueueInspectorVisible(true)}
              style={{ marginTop: 8, padding: 8, backgroundColor: '#007bff', borderRadius: 4 }}
            >
              {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
              <Text style={{ color: '#fff', fontSize: 12, textAlign: 'center' }}>
                전송 대기 항목 보기 ({count})
              </Text>
            </TouchableOpacity>
          )}
        </View>
        
        {/* 성공 메시지 표시 */}
        {successMessage && (
          // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
          <View style={{ backgroundColor: '#d4edda', padding: 12, borderRadius: 4, borderWidth: 1, borderColor: '#c3e6cb' }}>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <Text style={{ color: '#155724', fontSize: 14, fontWeight: 'bold' }}>✅ {successMessage}</Text>
          </View>
        )}
        
        {/* BFF 설정 오류 배너 */}
        {bffConfigError && (
          // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
          <View style={{ backgroundColor: '#fff3cd', padding: 12, borderRadius: 4, borderWidth: 1, borderColor: '#ffc107', marginBottom: 12 }}>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <Text style={{ color: '#856404', fontSize: 14, fontWeight: 'bold', marginBottom: 4 }}>
              ⚠️ BFF 설정 오류
            </Text>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <Text style={{ color: '#856404', fontSize: 12 }}>
              {bffConfigError.includes('연결') 
                ? 'BFF에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.'
                : 'BFF 설정 오류: URL 또는 API 키를 확인해 주세요.'}
            </Text>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <Text style={{ color: '#856404', fontSize: 11, marginTop: 4 }}>
              URL: {cfg.baseUrl || '(설정 안 됨)'} | Tenant: {cfg.tenantId || '(설정 안 됨)'}
            </Text>
          </View>
        )}
        
        {/* 큐 가득 참 오류 배너 */}
        {queueFullError && (
          // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
          <View style={{ backgroundColor: '#f8d7da', padding: 12, borderRadius: 4, borderWidth: 1, borderColor: '#f5c6cb', marginBottom: 12 }}>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <Text style={{ color: '#721c24', fontSize: 14, fontWeight: 'bold', marginBottom: 4 }}>
              ⚠️ 오프라인 큐가 가득 찼습니다
            </Text>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <Text style={{ color: '#721c24', fontSize: 12 }}>
              네트워크 복구 후 다시 시도해 주세요.
            </Text>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <TouchableOpacity 
              onPress={() => setQueueInspectorVisible(true)}
              style={{ marginTop: 8, padding: 8, backgroundColor: '#dc3545', borderRadius: 4 }}
            >
              {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
              <Text style={{ color: '#fff', fontSize: 12, textAlign: 'center' }}>
                큐 확인 및 정리
              </Text>
            </TouchableOpacity>
          </View>
        )}
        
        {/* 에러 메시지 표시 */}
        {errorMessage && (
          // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
          <View style={{ backgroundColor: '#fee', padding: 12, borderRadius: 4, borderWidth: 1, borderColor: '#fcc' }}>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
              <Text style={{ color: '#c00', fontSize: 14, fontWeight: 'bold', flex: 1 }}>
                ⚠️ {errorMessage}
              </Text>
              {errorDetails && (
                // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
                <TouchableOpacity onPress={() => setShowErrorDetails(!showErrorDetails)}>
                  {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
                  <Text style={{ color: '#c00', fontSize: 12, textDecorationLine: 'underline' }}>
                    {showErrorDetails ? '숨기기' : '자세히'}
                  </Text>
                </TouchableOpacity>
              )}
            </View>
            {showErrorDetails && errorDetails && (
              // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
              <Text style={{ color: '#666', fontSize: 12, marginTop: 8, fontFamily: 'monospace' }}>
                {errorDetails}
              </Text>
            )}
          </View>
        )}
        
        {/* 수동 검토 요청 뷰 */}
        {(manualReviewCount > 0 || lastManualReviewTime) && (
          // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
          <View style={{ backgroundColor: '#e7f3ff', padding: 8, borderRadius: 4, borderWidth: 1, borderColor: '#b3d9ff' }}>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <Text style={{ fontSize: 12, color: '#0066cc' }}>
              수동 검토 요청: {manualReviewCount}건 {isMock(cfg) ? '(오늘)' : ''}
            </Text>
            {lastManualReviewTime && (
              // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
              <Text style={{ fontSize: 11, color: '#666', marginTop: 4 }}>
                마지막 요청: {new Date(lastManualReviewTime).toLocaleString()}
              </Text>
            )}
          </View>
        )}
        {/* @ts-ignore - React Native JSX */}
        <QueueBadge count={count} lastSyncTs={lastSyncTs} />

        {/* @ts-ignore - React Native JSX */}
        <Text>설명</Text>
        {/* @ts-ignore - React Native JSX */}
        <TextInput value={desc} onChangeText={setDesc} style={{ borderWidth: 1, padding: 8 }} placeholder="설명" />

        {/* @ts-ignore - React Native JSX */}
        <Button title="추천(Suggest)" onPress={onSuggest} />
        {/* @ts-ignore - React Native JSX */}
        <Button title="승인(Approve)" onPress={onApprove} />
        {/* @ts-ignore - React Native JSX */}
        <Button title="Export 생성" onPress={onExport} />
        {/* @ts-ignore - React Native JSX */}
        <Button title="대사 세션 생성" onPress={onReconCreate} />
        {/* @ts-ignore - React Native JSX */}
        <Button title="대사 매칭(예: b1↔l1)" onPress={onReconMatch} />
        {/* @ts-ignore - React Native JSX */}
        <Button title="오프라인 큐 Flush" onPress={() => flushQueue(cfg)} />
        {/* @ts-ignore - React Native JSX */}
        <Button title="로컬 암호화 저장분 불러오기" onPress={onLoadLocal} />

        {/* @ts-ignore - React Native JSX */}
        <Text>Export Job: {exportJob?.jobId ?? '-'}</Text>
        {/* @ts-ignore - React Native JSX */}
        <Text>Recon Session: {sessionId || '-'}</Text>
        
        {/* Queue Inspector Modal */}
        <QueueInspector
          cfg={cfg}
          visible={queueInspectorVisible}
          onClose={() => setQueueInspectorVisible(false)}
        />
        {/* Leakage Firewall 차단 카드 */}
        {suggestOutBlocked?.blocked && suggestOutBlocked.reason_code && (
          // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
          <View style={{ marginTop: 12 }}>
            <WhyBlockCard reason_code={suggestOutBlocked.reason_code} />
          </View>
        )}
        
        {/* 추천 결과 리스트 (Risk 뱃지 포함) */}
        {!suggestOutBlocked?.blocked && suggestOut?.items && suggestOut.items.length > 0 && (
          // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
          <View style={{ marginTop: 12, gap: 8 }}>
            {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
            <Text style={{ fontSize: 16, fontWeight: 'bold' }}>추천 결과:</Text>
            {suggestOut.items.map((item: any, index: number) => {
              const risk = item.risk || { level: 'LOW', reasons: [], score: 0 };
              const riskColors = {
                HIGH: { bg: '#fee', text: '#c00', border: '#fcc' },
                MEDIUM: { bg: '#fff3cd', text: '#856404', border: '#ffc107' },
                LOW: { bg: '#e9ecef', text: '#6c757d', border: '#adb5bd' },
              };
              const color = riskColors[risk.level as keyof typeof riskColors] || riskColors.LOW;
              
              return (
                // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
                <View key={item.id || index} style={{ 
                  borderWidth: 1, 
                  borderColor: color.border, 
                  borderRadius: 4, 
                  padding: 12,
                  backgroundColor: color.bg,
                }}>
                  {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
                    <Text style={{ fontSize: 14, fontWeight: 'bold', flex: 1 }}>
                      {item.vendor || item.description || `항목 ${index + 1}`}
                    </Text>
                    {/* Risk 뱃지 */}
                    {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
                    <View style={{ 
                      backgroundColor: color.text, 
                      paddingHorizontal: 8, 
                      paddingVertical: 4, 
                      borderRadius: 4,
                    }}>
                      {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
                      <Text style={{ color: '#fff', fontSize: 12, fontWeight: 'bold' }}>
                        {risk.level === 'HIGH' ? '⚠️ HIGH' : risk.level === 'MEDIUM' ? '⚠ MEDIUM' : 'LOW'}
                      </Text>
                    </View>
                  </View>
                  {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
                  <Text style={{ fontSize: 12, color: '#666' }}>
                    금액: {item.amount?.toLocaleString() || '0'} {item.currency || 'KRW'}
                  </Text>
                  {risk.reasons && risk.reasons.length > 0 && (
                    // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
                    <Text style={{ fontSize: 11, color: color.text, marginTop: 4 }}>
                      이유: {risk.reasons.join(', ')}
                    </Text>
                  )}
                  {/* 엔진 출처 표시 */}
                  {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
                  <Text style={{ fontSize: 10, color: '#999', marginTop: 4, fontStyle: 'italic' }}>
                    {item.source === 'local-rule' 
                      ? 'ⓘ 이 추천은 온디바이스 규칙 엔진이 생성했습니다.'
                      : item.source === 'local-llm'
                      ? 'ⓘ 이 추천은 온디바이스 LLM 엔진이 생성했습니다.'
                      : 'ⓘ 이 추천은 BFF 서버에서 생성했습니다.'}
                  </Text>
                  {risk.level === 'HIGH' && (
                    // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
                    <View style={{ marginTop: 8, padding: 8, backgroundColor: '#fff', borderRadius: 4, borderWidth: 1, borderColor: color.border }}>
                      {/* @ts-expect-error - React Native JSX type compatibility issue with @types/react 18 */}
                      <Text style={{ fontSize: 12, color: color.text, fontWeight: 'bold', marginBottom: 8 }}>
                        ⚠ 고위험 거래 – 수동 검토 권장
                      </Text>
                      {/* 수동 검토 요청 버튼 */}
                      <ManualReviewButton
                        cfg={cfg}
                        subjectType="posting"
                        subjectId={item.id || `posting-${index}`}
                        reason="고위험 거래로 인한 수동 검토 요청"
                        reasonCode={risk.reasons?.[0] || 'HIGH_VALUE'}
                        amount={parseFloat(item.amount || '0')}
                        currency={item.currency || 'KRW'}
                        isHighValue={risk.level === 'HIGH'}
                        onSuccess={handleManualReviewSuccess}
                      />
                    </View>
                  )}
                  {/* 선택 버튼 */}
                  {/* @ts-ignore - React Native JSX */}
                  <Button 
                    title={`선택 (${index + 1}번)`}
                    onPress={() => setSelectedPostingIndex(index)}
                  />
                </View>
              );
            })}
          </View>
        )}
        
        {/* @ts-ignore - React Native JSX */}
        <Text selectable style={{ marginTop: 8 }}>
          결과 미리보기: {suggestOut ? JSON.stringify(suggestOut).slice(0, 400) : '-'}
        </Text>
        {/* @ts-ignore - React Native JSX */}
        {suggestOut?.items?.[0] && (() => {
          // 거래 금액 추출 (첫 번째 라인아이템의 amount 사용)
          const amount = parseFloat(desc.match(/\d+/)?.[0] || '0') || 4500; // 기본값 4500
          const currency = 'KRW'; // 기본값 KRW
          const HIGH_VALUE_THRESHOLD = 1000000; // 고액 거래 기준: 100만원
          const isHighValue = amount >= HIGH_VALUE_THRESHOLD;
          
          return (
            <ManualReviewButton
              cfg={cfg}
              subjectType="posting"
              subjectId={suggestOut.items?.[0]?.id || suggestOut.postings?.[0]?.id || 'unknown'}
              reason="수동 검토 필요"
              reasonCode={isHighValue ? 'HIGH_VALUE' : 'LOW_CONFIDENCE'}
              amount={amount}
              currency={currency}
              isHighValue={isHighValue}
            />
          );
        })()}
        {suggestOut?.rationale && (
          // @ts-expect-error - React Native JSX type compatibility issue with @types/react 18
          <Text style={{ marginTop: 8, fontSize: 12 }}>
            매칭 근거: {typeof suggestOut.rationale === 'string' ? suggestOut.rationale : JSON.stringify(suggestOut.rationale)}
          </Text>
        )}
      </ScrollView>
  );
}

