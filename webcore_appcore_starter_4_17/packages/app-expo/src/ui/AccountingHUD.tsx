/**
 * HUD 화면 (최소 동작형) — 승인/Export/대사 + 오프라인 큐 연동
 * 
 * @module app-expo/ui/AccountingHUD
 */

import React, { useEffect, useState } from 'react';
// @ts-ignore - React Native types
import { View, Text, Button, TextInput, ScrollView } from 'react-native';
import { ScreenPrivacyGate, useScreenPrivacy } from './hooks/useScreenPrivacy.js';
import { useOnline } from './hooks/useOnline.js';
import { useOfflineQueue } from './hooks/useOfflineQueue.js';
import { enqueue, flushQueue, startQueueAutoFlush } from './offline/offline-queue.js';
import QueueBadge from './components/QueueBadge.js';
import ManualReviewButton from './components/ManualReviewButton.js';
import {
  postSuggest,
  postApproval,
  postExport,
  postReconCreate,
  postReconMatch,
  type ClientCfg,
} from '../hud/accounting-api.js';
import { saveEncryptedReport, loadEncryptedReport } from '../security/secure-storage.js';

type Props = { cfg: ClientCfg };

export default function AccountingHUD({ cfg }: Props) {
  useScreenPrivacy();
  const online = useOnline();
  const { count, lastSyncTs } = useOfflineQueue();
  const [reportId, setReportId] = useState('demo-report-1');
  const [desc, setDesc] = useState('커피 영수증 4500원');
  const [suggestOut, setSuggestOut] = useState<any>(null);
  const [selectedPostingIndex, setSelectedPostingIndex] = useState<number>(0); // 선택된 posting index (0부터 시작)
  const [sessionId, setSessionId] = useState<string>('');
  const [exportJob, setExportJob] = useState<any>(null);

  useEffect(() => {
    startQueueAutoFlush(cfg);
  }, [cfg]);

  async function onSuggest() {
    const body = { items: [{ desc, amount: '4500', currency: 'KRW' }] };
    try {
      const out = await postSuggest(cfg, body);
      setSuggestOut(out);
      await saveEncryptedReport(reportId, out);
    } catch (e) {
      // 오프라인이면 큐에 넣고 종료
      await enqueue({ kind: 'suggest', body, idem: `idem_suggest_${Date.now()}` });
    }
  }

  async function onApprove() {
    const selectedIndex = selectedPostingIndex;
    const selectedPosting = suggestOut?.postings?.[selectedIndex];
    const id = selectedPosting?.id ?? suggestOut?.postings?.[0]?.id ?? 'sample-id';
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
    
    try {
      await postApproval(cfg, id, 'approve', 'OK', approvalOpts);
    } catch {
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
    }
  }

  async function onExport() {
    const idem = `idem_export_${Date.now()}`;
    try {
      const out = await postExport(
        cfg,
        { since: new Date(Date.now() - 7 * 86400000).toISOString(), limitDays: 7 },
        { idem }
      );
      setExportJob(out);
    } catch {
      await enqueue({
        kind: 'export',
        body: { since: new Date(Date.now() - 7 * 86400000).toISOString(), limitDays: 7 },
        idem,
      });
    }
  }

  async function onReconCreate() {
    const idem = `idem_recon_${Date.now()}`;
    const body = {
      bank: [{ id: 'b1', amount: '4500', date: new Date().toISOString(), currency: 'KRW' }],
      ledger: [{ id: 'l1', amount: '4500', date: new Date().toISOString(), currency: 'KRW', account: '8000' }],
    };
    try {
      const out = await postReconCreate(cfg, body, { idem });
      setSessionId(out.sessionId ?? out.id ?? '');
    } catch {
      await enqueue({ kind: 'recon_create', body, idem });
    }
  }

  async function onReconMatch() {
    if (!sessionId) {
      return;
    }
    const idem = `idem_match_${Date.now()}`;
    try {
      await postReconMatch(cfg, sessionId, 'b1', 'l1', { idem });
    } catch {
      await enqueue({ kind: 'recon_match', sessionId, bank_id: 'b1', ledger_id: 'l1', idem });
    }
  }

  async function onLoadLocal() {
    const data = await loadEncryptedReport(reportId);
    setSuggestOut(data);
  }

  return (
    <ScreenPrivacyGate>
      {/* @ts-ignore - React Native JSX */}
      <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
        {/* @ts-ignore - React Native JSX */}
        <QueueBadge count={count} lastSyncTs={lastSyncTs} />
        {/* @ts-ignore - React Native JSX */}
        <Text>네트워크: {online === null ? '...' : online ? '온라인' : '오프라인'}</Text>

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
        {/* @ts-ignore - React Native JSX */}
        <Text selectable style={{ marginTop: 8 }}>
          결과 미리보기: {suggestOut ? JSON.stringify(suggestOut).slice(0, 400) : '-'}
        </Text>
        {/* @ts-ignore - React Native JSX */}
        {suggestOut?.postings?.[0] && (() => {
          // 거래 금액 추출 (첫 번째 라인아이템의 amount 사용)
          const amount = parseFloat(desc.match(/\d+/)?.[0] || '0') || 4500; // 기본값 4500
          const currency = 'KRW'; // 기본값 KRW
          const HIGH_VALUE_THRESHOLD = 1000000; // 고액 거래 기준: 100만원
          const isHighValue = amount >= HIGH_VALUE_THRESHOLD;
          
          return (
            <ManualReviewButton
              cfg={cfg}
              subjectType="posting"
              subjectId={suggestOut.postings[0].id || 'unknown'}
              reason="수동 검토 필요"
              reasonCode={isHighValue ? 'HIGH_VALUE' : 'LOW_CONFIDENCE'}
              amount={amount}
              currency={currency}
              isHighValue={isHighValue}
            />
          );
        })()}
        {/* @ts-ignore - React Native JSX */}
        {suggestOut?.rationale && (
          <Text style={{ marginTop: 8, fontSize: 12 }}>
            매칭 근거: {typeof suggestOut.rationale === 'string' ? suggestOut.rationale : JSON.stringify(suggestOut.rationale)}
          </Text>
        )}
      </ScrollView>
    </ScreenPrivacyGate>
  );
}

