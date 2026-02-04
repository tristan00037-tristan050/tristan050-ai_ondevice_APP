# Golden Set QA 체크리스트

## 필수 항목

- [ ] 최소 50건 이상
- [ ] 각 항목: id, policy_version, input.line_items[], ground_truth.postings[]
- [ ] line_item: desc|description 중 1개 이상 + amount(string 숫자)
- [ ] posting: account(string), debit/credit(string 숫자)
- [ ] PII 없음(카드/계좌/주민/사업자/이메일)
- [ ] VAT/복합/경계/수동검토 케이스 포함
- [ ] measure:accuracy 결과 기록 및 변동 사유 메모
- [ ] 합성 보조 케이스(synthetic=true) 비율이 과도하지 않음 (최대 30%)
- [ ] 합성 보조는 desc/description만 보강하고 금액/통화/ground_truth는 변경 없음
- [ ] 최종 마감 전에 합성 보조 케이스를 실제/수작업 케이스로 순차 대체

## 검증 방법

```bash
# 골든셋 린터 실행
npm run ci:gold-size

# 정확도 측정
npm run measure:accuracy

# CI 게이트 확인
npm run ci:bench:accounting
```

## PII 패턴 (자동 감지)

- 연속 숫자 13~16자리 (카드/계좌 유사)
- 사업자등록번호 패턴: `XXX-XX-XXXXX`
- 주민등록번호 패턴: `XXXXXX-XXXXXXX`
- 이메일 주소

## 권장 구성 비율

- **단순(10~15)**: 소액 식비/교통/구독 (VAT 없음/단순)
- **VAT/세금(10~15)**: 공급가+세액 분리, 국내/해외, 역외 과세
- **복합(10~15)**: 다중 라인(상품+배송, 인건비+수수료 등)
- **경계/예외(10~20)**: 애매 설명, 수동 검토, 0/음수/비정상 고액

## 정확도 목표

- TOP-1 정확도: ≥70%
- TOP-5 정확도: ≥85%

## 참고

- `scripts/lint_golden_set.mjs` - 골든셋 린터
- `scripts/measure_accuracy.js` - 정확도 측정
- `scripts/bench_accounting_ci.mjs` - CI 게이트
- `docs/accounting/GOLDENSET_GUIDE.md` - 골든셋 확장 가이드

