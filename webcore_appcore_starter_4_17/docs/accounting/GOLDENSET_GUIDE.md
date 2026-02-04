# Golden Set 확장 가이드 (≥50건)

## 구성 권장 비율

- **단순(10~15)**: 소액 식비/교통/구독 (VAT 없음/단순)
- **VAT/세금(10~15)**: 공급가+세액 분리, 국내/해외, 역외 과세
- **복합(10~15)**: 다중 라인(상품+배송, 인건비+수수료 등)
- **경계/예외(10~20)**: 애매 설명, 수동 검토, 0/음수/비정상 고액

## JSON 예시 (datasets/gold/ledgers.json의 한 항목)

```json
{
  "id": "sample-0001",
  "policy_version": "acct-0.1",
  "input": {
    "line_items": [
      { "description": "커피 결제 스타벅스", "amount": "4800", "currency": "KRW" }
    ]
  },
  "ground_truth": {
    "postings": [
      { "account": "6020", "debit": "4800.00", "credit": "0.00", "currency": "KRW", "note": "커피 결제 스타벅스" }
    ]
  },
  "entries": [
    { "account": "1010", "debit": "4800.00", "credit": "0.00", "note": "커피 결제 스타벅스" },
    { "account": "6020", "debit": "0.00", "credit": "4800.00", "note": "커피 결제 스타벅스" }
  ],
  "currency": "KRW",
  "created_at": "2025-01-20T10:30:00Z"
}
```

## 필드 설명

- **id**: 고유 식별자 (선택)
- **policy_version**: 정책 버전 (선택)
- **input.line_items**: 입력 라인아이템 배열
  - `description` 또는 `desc`: 설명
  - `amount`: 금액 (문자열)
  - `currency`: 통화 코드 (ISO-4217, 선택)
- **ground_truth.postings**: 정답 분개 배열 (비용 계정만 포함 가능)
- **entries**: 전체 분개 항목 (차변/대변 쌍)
- **currency**: 기본 통화 (KRW)
- **created_at**: 생성 시간 (ISO8601 UTC)

## PII 처리 주의사항

> PII(계좌/카드/세금번호)는 `redact/redact_rules.accounting.json` 기준으로 마스킹 또는 샘플 텍스트만 사용하십시오.

## 검증 방법

```bash
# 정확도 측정
npm run measure:accuracy

# CI 게이트 (임계치: TOP-1≥70%, TOP-5≥85%)
npm run ci:bench:accounting
```


