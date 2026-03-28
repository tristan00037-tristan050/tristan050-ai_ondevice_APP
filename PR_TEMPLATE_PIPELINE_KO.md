# [AI-23] 범용 데이터 파이프라인 v2 (수집→정제→품질검증→학습투입, dry-run 완료)

## 개요
버틀러 범용 데이터 파이프라인 v2 구현 — 완전 온프레미스, 외부 전송 없음

## 7단계 파이프라인
1. `collector_v2.py`      : SHA-256 dedup + 6가지 파일 형식
2. `cleaner_v2.py`        : PII 5종 마스킹 + 한국어 0.5 + Unicode NFC
3. `quality_filter_v2.py` : hallucination 탐지 + 도메인별 기준 + n-gram 40%
4. `formatter_v2.py`      : prompt/completion + output_digest + template 검증
5. `splitter_v2.py`       : stratified split + leakage 검사
6. `pipeline_runner_v2.py`: 전체 오케스트레이션 + quarantine + dry/real 분리
7. `pipeline_manifest_v1.py`: git_sha + config_digest + counts 기록

## dry-run 검증 결과
- COMPILE_OK=1
- PIPELINE_VERIFY_OK=1
- pytest 전체 통과
- dry-run PIPELINE_RUN_OK=1
- SHELL_SYNTAX_OK=1

## 이 PR 범위
✅ 파이프라인 구조 완성 — dry-run 검증 완료  
❌ 실데이터 `/data/raw` 전체 실행 — 운영팀 범위

## 체크리스트
- [ ] 외부 URL 호출 코드 없음
- [ ] 응답/원문 content 로깅 코드 없음
- [ ] split taxonomy는 train/validation/test만 사용
- [ ] quarantine / manifest 저장 확인
- [ ] `__pycache__`, `*.pyc` 제거 완료
