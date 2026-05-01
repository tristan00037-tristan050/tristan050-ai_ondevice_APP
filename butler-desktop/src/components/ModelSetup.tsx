import { useEffect, useState } from 'react';
import { SIDECAR_BASE } from '../constants';

interface StatusData {
  status: 'ready' | 'no_model' | 'error';
  model_path?: string;
  last_error?: string;
}

export function ModelSetup({ onReady }: { onReady: () => void }) {
  const [data, setData] = useState<StatusData | null>(null);
  const [phase, setPhase] = useState<'starting' | 'checking' | 'failed' | 'ready'>('starting');
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const MAX_RETRIES = 30;
    const RETRY_INTERVAL = 1000;

    const checkStatus = async (attempt: number) => {
      if (cancelled) return;

      setRetryCount(attempt);

      if (attempt < 5) {
        setPhase('starting');
      } else {
        setPhase('checking');
      }

      try {
        const controller = new AbortController();
        const timeoutHandle = setTimeout(() => controller.abort(), 2000);

        const res = await fetch(`${SIDECAR_BASE}/api/model/status`, {
          signal: controller.signal,
        });

        clearTimeout(timeoutHandle);

        if (cancelled) return;

        if (res.ok) {
          const json = (await res.json()) as StatusData;
          setData(json);

          if (json.status === 'ready') {
            setPhase('ready');
            onReady();
            return;
          }
          // no_model 또는 error — 명시적 상태, 폴링 중지
          setPhase('failed');
          return;
        }
      } catch {
        if (cancelled) return;
        // 네트워크 에러 (sidecar 미기동) — 재시도
      }

      if (attempt < MAX_RETRIES) {
        timeoutId = setTimeout(() => checkStatus(attempt + 1), RETRY_INTERVAL);
      } else {
        setPhase('failed');
      }
    };

    checkStatus(0);

    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [onReady]);

  if (phase === 'ready') return null;

  if (phase === 'starting') {
    return (
      <div style={{
        padding: 16,
        background: '#e7f3ff',
        border: '1px solid #b8daff',
        borderRadius: 8,
        margin: 16,
      }}>
        <p style={{ margin: 0 }}>
          🔧 Butler 시작 중... ({retryCount}/30)
        </p>
        <p style={{ margin: '8px 0 0 0', fontSize: 12, color: '#666' }}>
          사이드카가 기동되는 동안 잠시만 기다려주세요.
        </p>
      </div>
    );
  }

  if (phase === 'checking') {
    return (
      <div style={{
        padding: 16,
        background: '#fff8e1',
        border: '1px solid #ffe082',
        borderRadius: 8,
        margin: 16,
      }}>
        <p style={{ margin: 0 }}>
          ⏳ Butler 응답 대기 중... ({retryCount}/30)
        </p>
        <p style={{ margin: '8px 0 0 0', fontSize: 12, color: '#666' }}>
          예상보다 시간이 걸리고 있습니다. 30초 후에도 응답이 없으면 다시 실행해주세요.
        </p>
      </div>
    );
  }

  if (data?.status === 'no_model') {
    return (
      <div style={{
        padding: 24,
        background: '#fff3cd',
        border: '1px solid #ffeaa7',
        borderRadius: 8,
        margin: 16,
      }}>
        <h3 style={{ margin: '0 0 12px 0' }}>🔧 Butler 모델 설치 필요</h3>
        <p style={{ margin: '0 0 8px 0' }}>
          Qwen3-4B 모델 (3.5GB)을 다운로드해야 합니다.
        </p>
        {data?.last_error && (
          <p style={{
            fontSize: 12,
            color: '#666',
            margin: '8px 0',
            fontFamily: 'monospace',
          }}>
            상세: {data.last_error}
          </p>
        )}
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: 'pointer' }}>수동 설치 방법</summary>
          <ol style={{ lineHeight: 1.8 }}>
            <li>HuggingFace 다운로드: <code>https://huggingface.co/Qwen/Qwen3-4B-GGUF</code></li>
            <li>저장 위치: <code>~/butler-models/qwen3-4b-q4_k_m.gguf</code></li>
            <li>환경변수 설정 후 Butler.app 재시작</li>
          </ol>
        </details>
      </div>
    );
  }

  // 30초 timeout 또는 error
  return (
    <div style={{
      padding: 24,
      background: '#f8d7da',
      border: '1px solid #f5c6cb',
      borderRadius: 8,
      margin: 16,
    }}>
      <h3 style={{ margin: '0 0 12px 0', color: '#721c24' }}>
        ⚠️ 사이드카 연결 실패
      </h3>
      <p style={{ margin: '0 0 8px 0' }}>
        30초 동안 sidecar 응답을 받지 못했습니다.
      </p>
      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: 'pointer' }}>진단 방법</summary>
        <ol style={{ lineHeight: 1.8, fontSize: 13 }}>
          <li>터미널에서 의존성 확인:
            <pre style={{ fontSize: 11, background: '#fff', padding: 8, borderRadius: 4 }}>
pip3 install -r requirements-serving.txt</pre>
          </li>
          <li>sidecar 직접 실행 테스트:
            <pre style={{ fontSize: 11, background: '#fff', padding: 8, borderRadius: 4 }}>
curl http://127.0.0.1:5903/api/model/status</pre>
          </li>
          <li>응답 있으면 Butler.app 종료 후 재실행</li>
        </ol>
      </details>
    </div>
  );
}
