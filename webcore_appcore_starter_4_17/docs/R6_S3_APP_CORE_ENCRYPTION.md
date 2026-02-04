# App Core — 로컬 암호화(At Rest)

## 개요

앱에서 생성된 회계 보고서를 로컬에 암호화하여 저장하는 기능입니다. AES-GCM 암호화를 사용하며, 키는 SecureStore에, 데이터는 MMKV에 저장됩니다.

## API

### 저장/로드

- `saveEncryptedReport(id, payload)` — 보고서 JSON 저장(AES-GCM, 키=SecureStore)
- `loadEncryptedReport<T>(id)` — 복호화 로드
- `deleteEncryptedReport(id)` — 단건 삭제
- `wipeAllEncryptedReports()` — 전체 삭제

### 키 관리

- `rotateLocalKey()` — 키 회전(모든 레코드 재암호화)

## 권장 UX 흐름

1. **HUD에서 회계 추천/승인/대사 호출** → 결과 JSON을 `saveEncryptedReport(reportId, payload)`로 저장
2. **상세 화면 진입 시** `loadEncryptedReport(reportId)`로 온디바이스 복호화
3. **로그아웃/디바이스 분실 대비**: `wipeAllEncryptedReports()` 실행

## 사용 예시

```typescript
import { saveEncryptedReport, loadEncryptedReport, postSuggest } from '@appcore/app-expo';

// 1. API 호출 후 결과 저장
const cfg = { baseUrl: 'http://localhost:8081', tenantId: 'default', apiKey: 'collector-key:operator' };
const result = await postSuggest(cfg, { items: [{ desc: '커피', amount: '4500', currency: 'KRW' }] });
await saveEncryptedReport('report-001', result);

// 2. 저장된 보고서 로드
const loaded = await loadEncryptedReport('report-001');
console.log(loaded);

// 3. 로그아웃 시 전체 삭제
await wipeAllEncryptedReports();
```

## 주의사항

- **WebCrypto SubtleCrypto 사용**: Expo SDK ≥50 권장. 구버전은 WebCrypto polyfill 필요.
- **대용량 데이터**: MMKV 기반이라 수십 MB까지 안정. 백업/이관 정책은 R7에서 정의.
- **키 회전**: `rotateLocalKey()`는 모든 레코드를 재암호화하므로 시간이 걸릴 수 있습니다.

## 보안 고려사항

- 키는 SecureStore에 저장되어 디바이스 키체인에 보호됩니다.
- 암호화 키는 앱 최초 실행 시 생성되며, 이후 재사용됩니다.
- 키 회전 시 모든 데이터를 재암호화하므로, 대량 데이터의 경우 백그라운드 작업으로 처리하는 것을 권장합니다.


