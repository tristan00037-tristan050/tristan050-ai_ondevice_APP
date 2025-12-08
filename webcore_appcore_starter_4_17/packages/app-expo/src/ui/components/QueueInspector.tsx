/**
 * Offline Queue Inspector 컴포넌트
 * 
 * 큐에 쌓인 항목을 보여주는 뷰
 * 
 * @module app-expo/ui/components/QueueInspector
 */

import React, { useEffect, useState } from 'react';
import { Modal, ScrollView, View, Text, Button, TouchableOpacity } from 'react-native';
import { listQueue, clearItem, type QueueItem } from '../offline/offline-queue';
import { getSecureKV } from '../../security/secure-storage';
import { isMock, type ClientCfg } from '../../hud/accounting-api';

const QUEUE_PREFIX = 'q:acct:';

interface QueueItemWithKey {
  key: string;
  item: QueueItem;
  createdAt: string;
  isExpired?: boolean;
  lastAttempt?: string;
  lastResult?: 'success' | 'failure';
  lastError?: string;
}

export default function QueueInspector({ 
  cfg, 
  visible, 
  onClose 
}: { 
  cfg: ClientCfg; 
  visible: boolean; 
  onClose: () => void;
}) {
  const [items, setItems] = useState<QueueItemWithKey[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (visible) {
      loadQueue();
    }
  }, [visible]);

  async function loadQueue() {
    setLoading(true);
    try {
      const kv = await getSecureKV();
      const keys = await listQueue();
      const queueItems: QueueItemWithKey[] = [];
      
      for (const key of keys) {
        try {
          const value = await kv.get(key);
          if (value) {
            const item = JSON.parse(value) as QueueItem;
            // 키에서 타임스탬프 추출 (it_${timestamp}_...)
            const timestamp = key.split('_')[1] || Date.now().toString();
            const createdAt = new Date(parseInt(timestamp)).toLocaleString();
            const age = Date.now() - parseInt(timestamp);
            const isExpired = age > 24 * 60 * 60 * 1000; // 24시간
            
            queueItems.push({
              key,
              item,
              createdAt,
              isExpired,
              // lastAttempt, lastResult는 추후 확장 가능
            });
          }
        } catch (e) {
          console.warn('Failed to parse queue item:', key, e);
        }
      }
      
      // 생성 시간 역순 정렬
      queueItems.sort((a, b) => {
        const tsA = parseInt(a.key.split('_')[1] || '0');
        const tsB = parseInt(b.key.split('_')[1] || '0');
        return tsB - tsA;
      });
      
      setItems(queueItems);
    } catch (e) {
      console.error('Failed to load queue:', e);
    } finally {
      setLoading(false);
    }
  }

  async function handleClearItem(key: string) {
    try {
      await clearItem(key);
      await loadQueue();
    } catch (e) {
      console.error('Failed to clear item:', e);
    }
  }

  function getKindLabel(kind: string): string {
    const labels: Record<string, string> = {
      'approval': '승인',
      'export': 'Export',
      'recon_create': '대사 생성',
      'recon_match': '대사 매칭',
      'suggest': '추천',
      'manual-review': '수동 검토',
    };
    return labels[kind] || kind;
  }

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={false}
      onRequestClose={onClose}
    >
      {/* @ts-expect-error - React Native JSX type compatibility issue */}
      <View style={{ flex: 1, padding: 16, backgroundColor: '#fff' }}>
        {/* @ts-expect-error - React Native JSX type compatibility issue */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          {/* @ts-expect-error - React Native JSX type compatibility issue */}
          <Text style={{ fontSize: 20, fontWeight: 'bold' }}>전송 대기 항목</Text>
          {/* @ts-expect-error - React Native JSX type compatibility issue */}
          <Button title="닫기" onPress={onClose} />
        </View>
        
        {isMock(cfg) && (
          // @ts-expect-error - React Native JSX type compatibility issue
          <View style={{ backgroundColor: '#fff3cd', padding: 12, borderRadius: 4, marginBottom: 16, borderWidth: 1, borderColor: '#ffc107' }}>
            {/* @ts-expect-error - React Native JSX type compatibility issue */}
            <Text style={{ fontSize: 12, color: '#856404' }}>
              ⚠️ Mock 모드: 실제 전송은 안 됩니다. (localStorage 기반)
            </Text>
          </View>
        )}
        
        {loading ? (
          // @ts-expect-error - React Native JSX type compatibility issue
          <Text style={{ textAlign: 'center', marginTop: 20 }}>로딩 중...</Text>
        ) : items.length === 0 ? (
          // @ts-expect-error - React Native JSX type compatibility issue
          <View style={{ alignItems: 'center', marginTop: 40 }}>
            {/* @ts-expect-error - React Native JSX type compatibility issue */}
            <Text style={{ fontSize: 16, color: '#666' }}>대기 중인 항목이 없습니다.</Text>
          </View>
        ) : (
          // @ts-expect-error - React Native JSX type compatibility issue
          <ScrollView>
            {items.map((queueItem) => (
              // @ts-expect-error - React Native JSX type compatibility issue
              <View key={queueItem.key} style={{ 
                borderWidth: 1, 
                borderColor: '#ddd', 
                borderRadius: 4, 
                padding: 12, 
                marginBottom: 12,
                backgroundColor: '#f9f9f9',
              }}>
                {/* @ts-expect-error - React Native JSX type compatibility issue */}
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
                  {/* @ts-expect-error - React Native JSX type compatibility issue */}
                  <Text style={{ fontSize: 14, fontWeight: 'bold' }}>
                    {getKindLabel(queueItem.item.kind)}
                  </Text>
                  {/* @ts-expect-error - React Native JSX type compatibility issue */}
                  <TouchableOpacity onPress={() => handleClearItem(queueItem.key)}>
                    {/* @ts-expect-error - React Native JSX type compatibility issue */}
                    <Text style={{ color: '#dc3545', fontSize: 12 }}>삭제</Text>
                  </TouchableOpacity>
                </View>
                
                {/* @ts-expect-error - React Native JSX type compatibility issue */}
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  {/* @ts-expect-error - React Native JSX type compatibility issue */}
                  <Text style={{ fontSize: 12, color: '#666' }}>
                    생성 시각: {queueItem.createdAt}
                  </Text>
                  {queueItem.isExpired && (
                    // @ts-expect-error - React Native JSX type compatibility issue
                    <Text style={{ fontSize: 10, color: '#dc3545', fontStyle: 'italic' }}>
                      (만료)
                    </Text>
                  )}
                </View>
                
                {queueItem.lastResult && (
                  // @ts-expect-error - React Native JSX type compatibility issue
                  <Text style={{ 
                    fontSize: 12, 
                    color: queueItem.lastResult === 'success' ? '#28a745' : '#dc3545',
                    marginTop: 4,
                  }}>
                    마지막 시도: {queueItem.lastResult === 'success' ? '성공' : '실패'}
                    {queueItem.lastError && ` (${queueItem.lastError})`}
                  </Text>
                )}
                
                {/* @ts-expect-error - React Native JSX type compatibility issue */}
                <Text style={{ fontSize: 10, color: '#999', marginTop: 4, fontFamily: 'monospace' }}>
                  ID: {queueItem.key.slice(QUEUE_PREFIX.length, QUEUE_PREFIX.length + 20)}...
                </Text>
              </View>
            ))}
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

