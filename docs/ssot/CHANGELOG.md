# SSOT ChangeLog (정본)

규칙
- SSOT_V1.md가 바뀌면, 이 파일도 반드시 같이 바뀌어야 합니다.
- 아래 4줄은 매번 꼭 씁니다: (무엇/왜/영향/검증)

## 2026-03-05
- 무엇: SSOT v1.0 최초 고정
- 왜: 전사 온디바이스 버틀러 + 내부 서버 옵션 + 운영형 강제 목표 확정
- 영향: 모든 개발/검증/데모는 SSOT만 기준으로 진행
- 검증: PR에서 SSOT 변경 시 ADR+CHANGELOG 없으면 차단

## 2026-03-04
- 무엇: SSOT_V1.md 완성 본문 반영(제품 정의·시스템 경계·버틀러·하드룰 12개·MVP·성능 지표 등)
- 왜: 정본을 플레이스홀더에서 실제 최종 목표 문서로 고정
- 영향: 레포/CI/검증 체인 기준이 동일 문서로 통일됨
- 검증: verify_ssot_change_discipline_v1 가드 통과

## 2026-03-05 (테스트 B)
- 무엇: SSOT 문구 1자 추가 후 CHANGELOG·ADR 동반 수정(가드 통과 검증)
- 왜: SSOT 변경 시 CHANGELOG+ADR 동반 강제가 동작하는지 확인
- 영향: 없음(테스트용)
- 검증: verify_repo_contracts.sh EXIT=0

## 2026-03-06 (회귀 테스트 B)
- 무엇: SSOT 1자 추가 + CHANGELOG·ADR 동반(가드 통과 검증)
- 왜: SSOT 변경 시 3종 동반 강제 회귀 테스트
- 영향: 없음(테스트)
- 검증: verify_repo_contracts.sh EXIT=0

## 2026-03-06 (DoD 매핑 SSOT 강제 테스트 B)
- 무엇: MODULE_DOD_KEYS_V1.json 포맷 1자 + CHANGELOG·ADR 동반
- 왜: DoD 매핑만 바꿀 때도 CHANGELOG+ADR 필수 회귀 확인
- 영향: 없음
- 검증: verify_repo_contracts.sh EXIT=0
