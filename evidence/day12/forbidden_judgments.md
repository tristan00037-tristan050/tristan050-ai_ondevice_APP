# PR #714 Forbidden Judgments (Day 12 거버넌스)

## PATCH 판정 영역에서 절대 금지

### 1. PROCEED 영역 금지
- production candidate 승인 표현 금지
- release 준비 완료 표현 금지 (영문 release-ready 류 포함)
- 베타 준비 완료 / 외부 베타 준비 완료 표현 금지

### 2. 외부 배포 영역 금지
- 외부 베타 배포 불가
- 사용자 노출 불가
- 자동 적용 기능 활성 불가

### 3. Butler 본체 통합 영역 금지
- Butler 본체 통합 PR 선착수 금지
- 본체 release 라인 진입 금지

### 4. 데이터셋 / 필드 영역 금지
- 정확도 단독 필드 (auto-apply accuracy 류) 사용 금지 (precision / recall 사용)
- 구버전 gold-v1 dataset 식별자 사용 금지 (card1_evalset_v1_1_500 만)

### 5. 모델 영역 금지
- 모델 교체 금지
- LoRA 학습 선착수 금지 (PR #715/#716 후 필요 시 PR #717)

### 6. 평가 영역 금지
- D mode 결과 과장 해석 금지
- A/B/C mode 결과를 official decision 으로 사용 금지
- metric threshold 변경 금지

## 허용 영역 (내부 알파)

- 내부 알파 검증 (auto_apply UI / 실행 OFF, manual review only)
- 개발팀 검증
- 라벨팀 오류 분석
- calibration 실험 (PR #715)
- extraction 분해 분석 (PR #716)

## 메인 팀 최종 문구 (PR #714 본문 포함 필수)

> Card 1 is safe enough for internal analysis, but not mature enough for production candidate or external beta.
