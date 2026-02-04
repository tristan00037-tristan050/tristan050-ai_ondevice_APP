# R8 준비 사항

## 개요

R8은 정확도·규칙 고도화를 위한 릴리스입니다. 리스크 스코어 엔진, 멀티테넌트 온보딩, 골든셋 확장을 포함합니다.

## 1. 정확도/리스크 모델 플러그인

### 목표
규칙/스코어 기반에 리스크/이상탐지 엔진을 플러그인 형태로 결합하고, 버저닝·A/B·롤백 가능

### 구현
- `packages/service-core-accounting/src/riskScoreEngine.ts`
  - `RiskScoreEngine` 인터페이스
  - `NoopRiskScore` 기본 구현
  - 엔진 레지스트리 시스템

### 사용법
```typescript
import { getRiskEngine, RiskInput } from '@appcore/service-core-accounting';

const engine = getRiskEngine();
const result = await engine.evaluate({
  tenant: 'default',
  ledgerEntry: { ... },
  context: { actor: 'user-1', requestId: 'req-123' }
});

console.log(`Risk Score: ${result.score}, Version: ${result.version}`);
```

### 환경변수
```bash
RISK_ENGINE=noop  # 기본값: noop, 향후 v1, v2 등 확장
```

### 플래그링
- 라벨: `risk_engine_version`을 `/metrics`에 노출
- A/B: 테넌트/비율 기반 스위칭
- Audit에 `engine_version` 기록

### 향후 확장
- `V1RiskScore`: 규칙 기반 리스크 평가
- `MLRiskScore`: 머신러닝 기반 이상탐지
- 버저닝 및 A/B 테스트 지원

## 2. 멀티테넌트 온보딩

### 목적
초기 템플릿 기반 테넌트 온보딩 자동화

### 템플릿
- `contracts/tenant_template.default.json`
  - 계정 매핑
  - 카테고리 목록
  - 정책 기본값
  - 어댑터 설정
  - 네트워크 정책

### 온보딩 스크립트
```bash
node scripts/onboard_tenant.mjs \
  --tenant=pilot-a \
  --template=contracts/tenant_template.default.json
```

### 보안/네트워크
- 어댑터 시크릿: 테넌트 스코프로 분리 (Kubernetes Secret)
- Egress allow-list: 테넌트별 네트워크 정책 (Helm values 레벨)

### 향후 구현
- DB에 테넌트 메타데이터 저장 (`tenant_metadata` 테이블)
- 자동 Secret 생성
- 네트워크 정책 자동 적용

## 3. 골든셋 확장 & 정확도 분석

### 데이터 요구사항
- 실데이터 기반 ≥100~200건
- 'ManualReview/오류' 라벨 포함

### 리포트 개선
`scripts/measure_accuracy.js` 확장:
- 계정별 breakdown
- 금액대별 breakdown
- 카테고리별 breakdown

### 사용법
```bash
node scripts/measure_accuracy.js \
  --golden-set=datasets/gold/ledgers.json \
  --output=accuracy_report.json \
  --breakdown=account,amount,category
```

### 출력 예시
```json
{
  "overall": {
    "top1": 0.72,
    "top5": 0.88
  },
  "breakdown": {
    "account": {
      "8000": { "top1": 0.75, "top5": 0.90 },
      "9000": { "top1": 0.70, "top5": 0.85 }
    },
    "amount": {
      "0-10000": { "top1": 0.80, "top5": 0.95 },
      "10000-100000": { "top1": 0.70, "top5": 0.85 }
    },
    "category": {
      "식비": { "top1": 0.75, "top5": 0.90 },
      "교통비": { "top1": 0.68, "top5": 0.83 }
    }
  },
  "manualReview": {
    "count": 15,
    "rate": 0.15
  },
  "errors": {
    "count": 5,
    "rate": 0.05
  }
}
```

### R8에서 활용
- 규칙/스코어 weight 조정 근거
- Low-confidence → 수동 검토 fallback 비율 최적화

## 4. 실행 계획

### Phase 1: 리스크 엔진 기본 구현 (완료)
- ✅ 인터페이스 정의
- ✅ NoopRiskScore 구현
- ✅ 엔진 레지스트리 시스템

### Phase 2: 멀티테넌트 온보딩 (완료)
- ✅ 템플릿 정의
- ✅ 온보딩 스크립트 구현

### Phase 3: 골든셋 확장 (진행 중)
- ⏳ 골든셋 데이터 수집 (≥100~200건)
- ⏳ 정확도 분석 스크립트 개선
- ⏳ 리포트 생성

### Phase 4: 규칙/스코어 튜닝
- ⏳ 골든셋 분석 결과 기반 weight 조정
- ⏳ Low-confidence threshold 최적화
- ⏳ A/B 테스트 설계

## 5. 수용 기준 (AC)

### 리스크 엔진
- ✅ 인터페이스 및 기본 구현 완료
- ⏳ V1RiskScore 구현
- ⏳ 메트릭 노출
- ⏳ Audit 로깅

### 멀티테넌트 온보딩
- ✅ 템플릿 및 스크립트 완료
- ⏳ DB 저장 구현
- ⏳ 자동 Secret 생성
- ⏳ 네트워크 정책 적용

### 골든셋 확장
- ⏳ ≥100~200건 데이터 수집
- ⏳ breakdown 리포트 생성
- ⏳ 규칙/스코어 튜닝 근거 확보

## 6. 참고 문서

- `docs/R7_FINAL_RELEASE_NOTES.md`: R7 릴리스 노트
- `docs/R7_RETRO.md`: R7 회고
- `docs/R7H_PILOT_GUIDE.md`: 파일럿 운영 가이드
- `contracts/tenant_template.default.json`: 테넌트 온보딩 템플릿
- `packages/service-core-accounting/src/riskScoreEngine.ts`: 리스크 엔진 인터페이스

## 3. R8-S1 RiskScoreEngine v1 스코프 (초안)

### 3.1 목적

- 범용 리스크 모델이 아닌, **"고액 거래 리스크 필터"**에 한정된 v1 엔진을 먼저 도입합니다.
- 고액 거래에 대해서만 보다 보수적인 승인/검토 플로우를 적용합니다.

### 3.2 동작

- 테넌트 설정에 따른 임계값(threshold) 이상인 거래에만 동작합니다.
  - 예) `amount >= 1,000,000` (테넌트별 설정값 사용)

- 리스크 엔진은 다음 정보를 반환합니다.
  - `score` (0.0 ~ 1.0)
  - `level` (`LOW` / `MEDIUM` / `HIGH`)
  - `reason` (예: `"HIGH_VALUE_TRANSACTION"`)

### 3.3 사용처

- Suggest / Approvals 플로우에서:
  - `level = HIGH` 인 경우:
    - 자동 승인 방지
    - Manual Review 큐로 강제 라우팅
    - Audit 이벤트에 `risk_score`, `risk_level`, `risk_reason` 기록

### 3.4 데이터 소스

- R7-H 파일럿 기간 동안의:
  - 고액 거래 + Manual Review 케이스
  - 규칙 위반/오류 패턴

을 기반으로 룰/threshold를 튜닝합니다.

## 4. 멀티테넌트 온보딩 템플릿 커스터마이징 가이드

`contracts/tenant_template.default.json` 기준으로, 다음 필드들은 고객사마다 반드시 검토/수정해야 합니다.

| 필드명                               | 설명                             | MUST_CUSTOMIZE |
|--------------------------------------|----------------------------------|----------------|
| `accounts[].code`                    | 계정 코드 매핑                   | YES            |
| `accounts[].description`             | 계정 설명 (고객사 용어)         | YES            |
| `categories[]`                       | 비용/수익 카테고리 구성         | YES            |
| `policies.manual_review_threshold`   | 수동 검토 기준 금액             | RECOMMENDED    |
| `policies.export_retention_days`     | Export 보존 기간                 | 기본값 사용 가능 |
| `locale`                             | 로케일 (예: `ko-KR`)            | YES            |
| `currency`                           | 기본 통화 (예: `KRW`)           | YES            |

- `MUST_CUSTOMIZE = YES` 인 항목은 온보딩 시 반드시 고객사별로 협의 후 설정해야 합니다.

