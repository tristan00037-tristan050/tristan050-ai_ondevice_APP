# User Consent Protocol

## metadata
- source_pr: 735
- branch: Option-C-Collection-Plan
- verdict: MEASURED_ONLY

## 목적

Internal Alpha 사용자로부터 manual suggestion feedback 을 수집하기 위한
동의 protocol. 한국 개인정보보호법 정합.

## 동의 항목

1. **feedback 수집 동의** — manual suggestion 에 대한 4 카테고리
   (useful / irrelevant / unsafe / needs_edit) 평가 수집.
2. **digest 저장 고지** — 원문은 저장하지 않으며 sha256 digest 만
   저장함을 고지.
3. **internal only 고지** — feedback 은 사내 폐쇄 환경에만 보관, 외부
   전송 없음.
4. **목적 한정** — feedback 은 카드 1 평가 품질 측정에만 사용, production
   decision 에 직접 반영하지 않음.

## opt-out path

- 사용자는 언제든 feedback 수집을 opt-out 할 수 있다.
- opt-out 시 해당 사용자의 기수집 digest 레코드는 삭제한다.
- opt-out 은 manual suggestion 기능 사용 자체를 막지 않는다.

## 동의 시점

정식 Internal Alpha 진입 시 1회 동의 + 수시 철회 가능.

## 비식별화

- suggestion context 는 digest (sha256) 로만 저장.
- reviewer 평가 기록(`reviewer_id`)은 사내 reviewer 식별자 — 사용자
  개인정보 아님.

## 본 PR 범위

본 PR 은 동의 protocol 을 정착한다. 실제 동의 수집 UI/운영은 별도 운영
단계.
