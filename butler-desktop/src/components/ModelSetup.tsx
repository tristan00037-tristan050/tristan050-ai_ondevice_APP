import React, { useEffect, useState } from 'react';
import { SIDECAR_BASE } from '../constants';

type ModelStatus = 'ready' | 'no_model' | 'loading' | 'error';

interface StatusData {
  status: ModelStatus;
  model_path: string;
  last_error: string;
}

export function ModelSetup() {
  const [data, setData] = useState<StatusData | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch(`${SIDECAR_BASE}/api/model/status`);
        if (!cancelled && res.ok) {
          const json = (await res.json()) as StatusData;
          setData(json);
        }
      } catch {
        if (!cancelled) {
          setData({ status: 'error', model_path: '', last_error: 'sidecar 연결 실패 — butler_sidecar.py 실행 여부를 확인해주세요.' });
        }
      } finally {
        if (!cancelled) setChecked(true);
      }
    };

    poll();
    const interval = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (!checked || !data || data.status === 'ready') return null;

  return (
    <div
      data-testid="model-setup"
      style={{
        background: '#fff7e6',
        border: '1px solid #fa8c16',
        borderRadius: 8,
        padding: 16,
        marginBottom: 16,
      }}
    >
      {data.status === 'error' && (
        <>
          <strong>⚠️ 사이드카 오류</strong>
          <p style={{ margin: '8px 0 0', fontSize: 13, color: '#cf1322' }}>
            {data.last_error}
          </p>
        </>
      )}
      {data.status === 'no_model' && (
        <>
          <strong>📦 모델 파일 필요</strong>
          <p style={{ margin: '8px 0 0', fontSize: 13 }}>
            <code>BUTLER_MODEL_PATH</code> 환경변수에 .gguf 모델 경로를 설정하고 사이드카를 재시작하세요.
            <br />
            자세한 안내: <code>docs/beta/getting_started_v1.md</code> 1.5절
          </p>
        </>
      )}
      {data.status === 'loading' && (
        <>
          <strong>⏳ 모델 로딩 중…</strong>
          <p style={{ margin: '8px 0 0', fontSize: 13 }}>잠시 기다려주세요. 첫 로딩은 1~3분 소요됩니다.</p>
        </>
      )}
    </div>
  );
}
