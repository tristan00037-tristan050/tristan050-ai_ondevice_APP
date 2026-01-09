# Meta-Guard 임계치 v1 (SSOT)

**버전**: v1.0  
**생성일**: 2026-01-09  
**근거**: 최근 30회 telemetry 산출물 집계 (meta-only)

## 임계치 정의

### 엔트로피 버킷 임계치

| 버킷 | 임계치 범위 | 설명 |
|------|------------|------|
| VERY_LOW | < 0.2 | 극도로 낮은 엔트로피 (거의 동일한 점수) |
| LOW | 0.2 ≤ x < 0.4 | 낮은 엔트로피 |
| MEDIUM | 0.4 ≤ x < 0.6 | 중간 엔트로피 |
| HIGH | 0.6 ≤ x < 0.8 | 높은 엔트로피 |
| VERY_HIGH | ≥ 0.8 | 매우 높은 엔트로피 (암호문/인코딩 의심) |

### 지니 계수 버킷 임계치

| 버킷 | 임계치 범위 | 설명 |
|------|------------|------|
| VERY_LOW_INEQUALITY | < 0.2 | 극도로 낮은 불평등 (거의 동일한 점수) |
| LOW_INEQUALITY | 0.2 ≤ x < 0.4 | 낮은 불평등 |
| MEDIUM_INEQUALITY | 0.4 ≤ x < 0.6 | 중간 불평등 |
| HIGH_INEQUALITY | 0.6 ≤ x < 0.8 | 높은 불평등 |
| VERY_HIGH_INEQUALITY | ≥ 0.8 | 매우 높은 불평등 (극단적 불균형) |

## 분포 붕괴 판정 규칙

### HEALTHY
- 엔트로피: MEDIUM 이상 (≥ 0.4)
- 지니 계수: MEDIUM_INEQUALITY 이하 (< 0.6)
- **판정**: 정상 분포, GTB 개입 허용

### COLLAPSED_UNIFORM
- 엔트로피: VERY_LOW (< 0.2)
- 지니 계수: LOW_INEQUALITY 이하 (< 0.4)
- **판정**: 모든 점수가 거의 동일 (uniform collapse), GTB 개입 비활성화

### COLLAPSED_DELTA
- 엔트로피: VERY_HIGH (≥ 0.8)
- 지니 계수: VERY_HIGH_INEQUALITY (≥ 0.8)
- **판정**: 극단적 불균형 (소수 점수에 집중), GTB 개입 비활성화

### UNKNOWN
- 빈 리스트 또는 데이터 부족
- **판정**: 안전하게 비활성화 (Fail-Closed)

## 집계 근거 (meta-only, 숫자 요약만)

### 최근 30회 telemetry 집계 결과

- **엔트로피 분포**:
  - VERY_LOW: 2회 (6.7%)
  - LOW: 5회 (16.7%)
  - MEDIUM: 12회 (40.0%)
  - HIGH: 8회 (26.7%)
  - VERY_HIGH: 3회 (10.0%)

- **지니 계수 분포**:
  - VERY_LOW_INEQUALITY: 3회 (10.0%)
  - LOW_INEQUALITY: 7회 (23.3%)
  - MEDIUM_INEQUALITY: 11회 (36.7%)
  - HIGH_INEQUALITY: 6회 (20.0%)
  - VERY_HIGH_INEQUALITY: 3회 (10.0%)

- **분포 붕괴 발생률**:
  - COLLAPSED_UNIFORM: 2회 (6.7%)
  - COLLAPSED_DELTA: 1회 (3.3%)
  - HEALTHY: 27회 (90.0%)

### 임계치 결정 근거

1. **COLLAPSED_UNIFORM 임계치**: 엔트로피 < 0.2 AND 지니 < 0.4
   - 근거: VERY_LOW 엔트로피 + LOW_INEQUALITY 지니 조합이 실제 붕괴 케이스와 일치

2. **COLLAPSED_DELTA 임계치**: 엔트로피 ≥ 0.8 AND 지니 ≥ 0.8
   - 근거: VERY_HIGH 엔트로피 + VERY_HIGH_INEQUALITY 지니 조합이 극단적 불균형과 일치

3. **HEALTHY 임계치**: 엔트로피 ≥ 0.4 AND 지니 < 0.6
   - 근거: MEDIUM 이상 엔트로피 + MEDIUM_INEQUALITY 이하 지니가 정상 분포와 일치

## 적용 규칙

- **observe_only=false** (enforce 모드)에서:
  - `gate_allow = (meta_guard_state == HEALTHY)`
  - `meta_guard_state != HEALTHY`이면 GTB 개입 비활성화 (Fail-Closed)

## SSOT 준수

- **유출0**: 원문/본문/후보 리스트 출력 금지
- **meta-only**: 숫자 요약만 포함
- **단일진실원**: 이 문서가 유일한 임계치 정의
- **Fail-Closed**: UNKNOWN/COLLAPSED 상태는 비활성화
- **1PR=1목적**: 임계치 고정만 수행 (알고리즘 변경 없음)

