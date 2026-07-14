# v2.8 구현·검증 보고서

## 결론

첨부 지시서의 90개 acceptance, 60개 attack/mutation, 46개 결함을 코드·테스트·독립 검증기·12-job CI 계약에 연결했습니다. 이번 전달본에서 실제로 확인한 범위는 로컬 구현 계약이며, 실제 Butler 저장소·승인 정책·서명 CI·M3 Max 실측 증거가 없으므로 제품 편입 완료나 M3/G1 PASS는 선언하지 않습니다.

## 정본 교정

1. 본문 일부의 `58개 공격` 표기는 실제 CSV 60행과 충돌하므로 60행을 정본으로 채택했습니다.
2. 원본 결함 추적표의 영역 오매핑은 결함 제목과 실패 경로를 기준으로 46행 전부 명시적으로 다시 연결했습니다.
3. Metal `currentAllocatedSize == 0`은 할당 전 정상 상태일 수 있으므로 음수·모순 상태만 차단합니다.
4. 대표 fixture warmup은 지시서의 epoch당 candidate별 2회, 총 4회로 고정했습니다.
5. M4 전 G1 선언을 막기 위해 `G1_READY`를 final-status schema에서 제거했습니다.
6. receipt 없는 코드 전달본은 M3 artifact PASS가 아니므로 독립 검증기의 `code-delivery`와 `m3-evidence` 모드를 분리했습니다.
7. Sigstore는 payload를 subject로 결속한 in-toto Statement를 먼저 검증하고, 그 Statement 자체를 공식 `cosign verify-blob` 흐름으로 재검증하도록 교정했습니다.

## 검증 결과

- Python 표준 라이브러리 기반 자동시험: 74/74 PASS
- 공격 계약: 60/60 expected block
- acceptance 추적: 90/90 분류 완료
- 결함 추적: 46/46 명시적 재매핑 완료
- producer 비의존 offline verifier 정적 독립성 검사: PASS
- 코드 전달 artifact closed manifest 독립 재검증: PASS 대상

## 2026 기준 벤치마크 반영

MLPerf Client v1.6과 MLPerf Mobile v6.0의 온디바이스 LLM 평가 방향, SLSA v1.2 Source 요구사항, in-toto Statement v1, RFC 8785/JCS, JSON Schema 2020-12, Sigstore keyless bundle 검증을 설계 기준으로 반영했습니다. 세부 링크와 적용 범위는 `BENCHMARK_REFERENCES_2026.md`에 기록했습니다.

## 남은 실제 소유자 입력

승인된 전체 Git commit/tree OID, 실제 제품 모듈과 entrypoint, 1.7B·4B 모델, fixture/evaluator/runtime 매니페스트, benchmark/trust/scanner 정책, CI identity, M3 Max의 OS egress·memory·Metal·energy 증거가 필요합니다. 입력 전 모든 시작 게이트는 false이며 runtime activation은 0입니다.
