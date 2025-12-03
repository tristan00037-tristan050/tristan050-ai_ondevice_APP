# Reconciliation Adapter (Draft)

## Purpose

- 외부 원장/거래원장(은행, PG, ERP) 트랜잭션을 내부 `bank[]/ledger[]` 표준으로 변환.

## Adapter Interface (v0)

```typescript
export type ReconSource = 'BANK' | 'PG' | 'ERP';

export type ReconAdapter = {
  id: string;
  source: ReconSource;
  load(input: unknown): Promise<{ bank: any[]; ledger: any[] }>;
};
```

## Mapping Rules

### 금액
- **입력**: string (정수/소수점·구분자 허용)
- **내부**: `parseAmount()`로 정규화

### 통화
- **입력**: ISO-4217 코드 (예: `KRW`, `USD`)
- **검증**: `pattern: "^[A-Z]{3}$"`

### 날짜
- **입력**: ISO 문자열 (UTC 또는 로컬)
- **내부**: UTC 변환 후 저장

### PII
- 계좌/카드 식별자는 hash/tokenize 후 저장
- 원본 데이터는 레드랙션 규칙 적용

## QA

### 샘플 테스트
- 샘플 10건 이상 → `tests/accounting_recon_e2e.mjs`로 세션 생성 성공 여부 확인

### KPI
- `unmatched_*` 비율을 KPI로 기록
- 매칭 정확도 (confidence ≥ 0.8 비율)
- 수동 매칭 비율


