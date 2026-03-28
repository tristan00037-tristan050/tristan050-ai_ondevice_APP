# [AI-22] OpenAI 호환 버틀러 서빙 서버 (stub 완성, 모델 연결 대기)

## 개요
OpenAI 호환 버틀러 서빙 서버 구현 — 완전 온프레미스, 외부 전송 없음

## 엔드포인트
- GET `/healthz`
- GET `/health/readyz`
- GET `/v1/models`
- POST `/v1/chat/completions`
- GET `/version`
- GET `/metrics`

## dry-run 검증 결과
- COMPILE_OK=1
- pytest 전체 통과
- BUTLER_SERVER_SCHEMA_OK=1
- BUTLER_REQUEST_ID_OK=1
- SHELL_SYNTAX_OK=1
- stub direct run 확인

## 범위
- 서버 구조 및 테스트 완성
- 실제 모델 연결은 `adapter_model.safetensors` 준비 후 진행
