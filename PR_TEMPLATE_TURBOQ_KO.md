# [AI-21] TurboQuant KV 캐시 압축 통합 (server/mobile scaffold + verify + benchmark)

## 개요
TurboQuant(논문-정합 구현) KV 캐시 압축 통합
Google ICLR 2026 PolarQuant + QJL 2단계 압축 — 재학습 불필요

## 변경 사항
- `turboq_core_v1.py`: PolarQuant + QJL 핵심 엔진 (deterministic fallback 포함)
- `turboq_butler_hook_v1.py`: wrapper 모드 기본, fail-closed 폴백 경로 명시
- `turboq_server_v1.py`: API 스키마 불변, status endpoint scaffold
- `turboq_mobile_v1.py`: 설정 계산기 + MNN 연결 계획 (실제 삽입은 실행팀)
- `turboq_benchmark_v1.py`: dry-run/GPU 분리, 가짜 measured_* 금지
- `turboq_verify_v1.py`: GPU 불필요 항목 PASS, skipped_checks 기록

## dry-run 검증 결과 (맥북/리눅스 로컬)
- `COMPILE_OK=1`
- `TURBOQ_VERIFY_OK=1`
- Lloyd-Max MSE < 0.1
- inner-product bias < 0.05 (normalized-vector CPU smoke)
- pytest 전체 통과
- `SHELL_SYNTAX_OK=1`

## 이 PR 범위
✅ 코드 파이프라인 완성 — 논문-정합 구현, dry-run 완료
❌ GPU 벤치마크 / 모바일 실기기 측정 — 실행팀 직접 수행
❌ 공식 Google 코드 아님 — research-faithful scaffold
