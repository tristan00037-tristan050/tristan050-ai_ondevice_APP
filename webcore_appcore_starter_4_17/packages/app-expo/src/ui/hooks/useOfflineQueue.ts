import { useEffect, useState } from 'react';
import { listQueue } from '../offline/offline-queue';

// 간단한 타임스탬프 저장 (SecureStorage 사용)
async function getLastSyncTs(): Promise<number | undefined> {
  try {
    const { getSecureKV } = await import('../../security/secure-storage.js');
    const kv = await getSecureKV();
    const ts = kv.getString('last_sync_ts');
    return ts ? parseInt(ts, 10) : undefined;
  } catch {
    return undefined;
  }
}

export function useOfflineQueue() {
  const [count, setCount] = useState(0);
  const [lastSyncTs, setLastSyncTs] = useState<number | undefined>();

  useEffect(() => {
    const update = async () => {
      const keys = await listQueue();
      setCount(keys.length);
      const ts = await getLastSyncTs();
      setLastSyncTs(ts);
    };

    update();
    const t = setInterval(update, 1500);
    return () => clearInterval(t);
  }, []);

  return { count, lastSyncTs };
}

