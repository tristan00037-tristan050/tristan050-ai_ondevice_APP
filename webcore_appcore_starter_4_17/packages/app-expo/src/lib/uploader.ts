/**
 * Collector 업로더 (즉시/큐/플러시)
 * 지수 백오프, 최대 시도, 네트워크 상태 연계
 * 
 * @module uploader
 */

import * as NetInfo from '@react-native-community/netinfo';
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface UploadOptions {
  /** Collector 엔드포인트 URL */
  collectorUrl: string;
  /** API 키 */
  apiKey: string;
  /** 테넌트 ID */
  tenantId: string;
  /** 최대 재시도 횟수 (기본: 5) */
  maxRetries?: number;
  /** 초기 백오프 지연 시간(ms) (기본: 1000) */
  initialBackoffMs?: number;
  /** 최대 백오프 지연 시간(ms) (기본: 30000) */
  maxBackoffMs?: number;
  /** 백오프 배수 (기본: 2) */
  backoffMultiplier?: number;
  /** 네트워크 상태 확인 여부 (기본: true) */
  checkNetworkState?: boolean;
}

export interface QueuedItem {
  id: string;
  report: unknown;
  md?: string; // 레드랙션 적용된 마크다운 (옵션)
  tenantId: string; // 테넌트 ID만 저장 (API Key는 저장하지 않음)
  attempt: number; // 재시도 횟수
  createdAt: number; // 생성 시각
  lastError?: string;
}

const QUEUE_STORAGE_KEY = '@qc_upload_queue';
const MAX_QUEUE_SIZE = 100;

// NetInfo 리스너 중복 등록 방지
let netInfoListener: (() => void) | null = null;
let isNetInfoListenerRegistered = false;

/**
 * 지수 백오프 계산 (지터 포함)
 */
function calculateBackoff(
  retryCount: number,
  initialBackoffMs: number,
  maxBackoffMs: number,
  multiplier: number
): number {
  const backoff = initialBackoffMs * Math.pow(multiplier, retryCount);
  const clamped = Math.min(backoff, maxBackoffMs);
  // ±1초 지터 추가 (동시 재시도 분산)
  const jitter = (Math.random() * 2000) - 1000; // -1000ms ~ +1000ms
  return Math.max(0, clamped + jitter);
}

/**
 * 네트워크 상태 확인
 */
async function checkNetworkAvailable(): Promise<boolean> {
  const state = await NetInfo.fetch();
  return state.isConnected ?? false;
}

/**
 * 리포트를 Collector에 업로드
 */
async function uploadToCollector(
  report: unknown,
  options: UploadOptions
): Promise<{ success: boolean; error?: string }> {
  try {
    // 네트워크 상태 확인
    if (options.checkNetworkState !== false) {
      const isConnected = await checkNetworkAvailable();
      if (!isConnected) {
        return {
          success: false,
          error: 'Network not available',
        };
      }
    }

    const response = await fetch(`${options.collectorUrl}/ingest/qc`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Api-Key': options.apiKey,
        'X-Tenant': options.tenantId,
      },
      body: JSON.stringify(report),
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      return {
        success: false,
        error: `HTTP ${response.status}: ${errorText}`,
      };
    }

    return { success: true };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

/**
 * 큐에서 항목 로드
 */
async function loadQueue(): Promise<QueuedItem[]> {
  try {
    const data = await AsyncStorage.getItem(QUEUE_STORAGE_KEY);
    if (!data) return [];
    return JSON.parse(data);
  } catch (error) {
    console.error('Failed to load upload queue:', error);
    return [];
  }
}

/**
 * 큐에 항목 저장
 */
async function saveQueue(queue: QueuedItem[]): Promise<void> {
  try {
    // 큐 크기 제한
    const limitedQueue = queue.slice(-MAX_QUEUE_SIZE);
    await AsyncStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(limitedQueue));
  } catch (error) {
    console.error('Failed to save upload queue:', error);
  }
}

/**
 * 리포트를 즉시 업로드 시도 (실패 시 큐에 추가)
 */
export async function uploadReport(
  report: unknown,
  options: UploadOptions
): Promise<{ success: boolean; queued: boolean; error?: string }> {
  const maxRetries = options.maxRetries ?? 5;
  const initialBackoffMs = options.initialBackoffMs ?? 1000;
  const maxBackoffMs = options.maxBackoffMs ?? 30000;
  const backoffMultiplier = options.backoffMultiplier ?? 2;

  // 즉시 업로드 시도
  let retryCount = 0;
  while (retryCount < maxRetries) {
    const result = await uploadToCollector(report, options);
    
    if (result.success) {
      return { success: true, queued: false };
    }

    // 마지막 시도가 아니면 백오프 후 재시도
    if (retryCount < maxRetries - 1) {
      const backoff = calculateBackoff(
        retryCount,
        initialBackoffMs,
        maxBackoffMs,
        backoffMultiplier
      );
      await new Promise(resolve => setTimeout(resolve, backoff));
      retryCount++;
    } else {
      // 모든 재시도 실패 시 큐에 추가
      // 주의: API Key는 큐에 저장하지 않음 (메모리/옵션으로만 사용)
      const queue = await loadQueue();
      const item: QueuedItem = {
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        report,
        tenantId: options.tenantId, // 테넌트 ID만 저장
        attempt: 0,
        createdAt: Date.now(),
        lastError: result.error,
      };
      queue.push(item);
      await saveQueue(queue);
      
      return {
        success: false,
        queued: true,
        error: result.error,
      };
    }
  }

  return {
    success: false,
    queued: false,
    error: 'Max retries exceeded',
  };
}

/**
 * 큐에 있는 모든 항목을 플러시 (재시도)
 */
export async function flushQueue(
  options: UploadOptions
): Promise<{ success: number; failed: number; errors: string[] }> {
  const queue = await loadQueue();
  if (queue.length === 0) {
    return { success: 0, failed: 0, errors: [] };
  }

  const maxRetries = options.maxRetries ?? 5;
  const initialBackoffMs = options.initialBackoffMs ?? 1000;
  const maxBackoffMs = options.maxBackoffMs ?? 30000;
  const backoffMultiplier = options.backoffMultiplier ?? 2;

  const results = {
    success: 0,
    failed: 0,
    errors: [] as string[],
  };

  const remainingQueue: QueuedItem[] = [];

  for (const item of queue) {
    let attempt = item.attempt;
    let uploaded = false;

    // 큐 항목의 tenantId와 옵션의 tenantId 일치 확인
    if (item.tenantId !== options.tenantId) {
      console.warn(`Skipping item ${item.id}: tenant mismatch`);
      remainingQueue.push(item);
      results.failed++;
      results.errors.push(`Item ${item.id}: tenant mismatch`);
      continue;
    }

    while (attempt < maxRetries && !uploaded) {
      const result = await uploadToCollector(item.report, options);
      
      if (result.success) {
        results.success++;
        uploaded = true;
      } else {
        // 백오프 후 재시도
        if (attempt < maxRetries - 1) {
          const backoff = calculateBackoff(
            attempt,
            initialBackoffMs,
            maxBackoffMs,
            backoffMultiplier
          );
          await new Promise(resolve => setTimeout(resolve, backoff));
          attempt++;
        } else {
          // 재시도 실패 - 큐에 다시 추가 (attempt 증가)
          item.attempt = attempt + 1;
          item.lastError = result.error;
          remainingQueue.push(item);
          results.failed++;
          results.errors.push(`Item ${item.id}: ${result.error}`);
          break;
        }
      }
    }
  }

  // 남은 항목 저장
  await saveQueue(remainingQueue);

  return results;
}

/**
 * 큐 상태 조회
 */
export async function getQueueStatus(): Promise<{
  count: number;
  oldestTimestamp?: number;
  newestTimestamp?: number;
}> {
  const queue = await loadQueue();
  
  if (queue.length === 0) {
    return { count: 0 };
  }

  const timestamps = queue.map(item => item.createdAt);
  return {
    count: queue.length,
    oldestTimestamp: Math.min(...timestamps),
    newestTimestamp: Math.max(...timestamps),
  };
}

/**
 * NetInfo 리스너 등록 (중복 방지)
 * 네트워크 복구 시 자동으로 큐 플러시
 */
export function ensureNetinfoFlusher(
  options: UploadOptions
): void {
  if (isNetInfoListenerRegistered) {
    return; // 이미 등록됨
  }

  netInfoListener = NetInfo.addEventListener(state => {
    if (state.isConnected) {
      // 네트워크 복구 시 큐 플러시
      flushQueue(options).catch(error => {
        console.error('Failed to flush queue on network recovery:', error);
      });
    }
  });

  isNetInfoListenerRegistered = true;
}

/**
 * NetInfo 리스너 해제
 */
export function removeNetinfoFlusher(): void {
  if (netInfoListener) {
    netInfoListener();
    netInfoListener = null;
    isNetInfoListenerRegistered = false;
  }
}

/**
 * 큐 초기화 (주의: 모든 대기 중인 업로드가 삭제됩니다)
 */
export async function clearQueue(): Promise<void> {
  await AsyncStorage.removeItem(QUEUE_STORAGE_KEY);
}

