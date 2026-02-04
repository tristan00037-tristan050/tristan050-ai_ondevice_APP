# R6-S3.2 — HUD UI 통합 가이드

## 1) HUD 스크린 사용 예 (Expo App)

```tsx
import React from 'react';
import { AccountingHUD } from '@appcore/app-expo';

export default function Screen() {
  return (
    <AccountingHUD cfg={{
      baseUrl: 'http://localhost:8081',
      tenantId: 'default',
      apiKey: 'collector-key:operator'
    }}/>
  );
}
```

## 2) 보안 UX

- 앱이 백그라운드로 전환되면 BlurView 오버레이 + 스크린캡처 차단.
- 민감 필드는 RedactedText(탭 시 토글) 사용 권장.

## 3) 오프라인 큐

- 승인/Export/대사/추천 요청 실패 시 자동으로 암호화 저장.
- 온라인 전환(NetInfo) 또는 수동 "Flush" 시 재전송.
- 모든 요청은 Idempotency-Key를 유지하여 서버 중복 처리 방지.

## 4) 컴포넌트 API

### AccountingHUD
- Props: `cfg: ClientCfg` (baseUrl, tenantId, apiKey)
- 기능: Suggest/Approval/Export/Reconciliation UI + 오프라인 큐 연동

### RedactedText
- Props: `value: string`, `masked?: boolean`
- 기능: 민감 정보 마스킹/토글

### useOnline
- 반환: `boolean | null` (온라인 상태)

### useScreenPrivacy
- 기능: 스크린캡처 차단 + 백그라운드 블러

### ScreenPrivacyGate
- Props: `children: React.ReactNode`
- 기능: 백그라운드 시 BlurView 오버레이

## 5) 오프라인 큐 API

### enqueue(item: QueueItem)
- 오프라인 요청을 암호화 저장

### flushQueue(cfg: ClientCfg)
- 큐에 저장된 요청을 재전송

### startQueueAutoFlush(cfg: ClientCfg)
- 온라인 전환 시 자동으로 큐 flush

### listQueue()
- 큐에 저장된 항목 목록 반환


