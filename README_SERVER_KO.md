# Butler AI OpenAI 호환 서빙 서버 가이드 (AI-22)

이 번들은 OpenAI **서버**를 사용하는 것이 아니라, OpenAI **Chat Completions 형식**을 내부망에서 그대로 흉내 내는 온프레미스 서버입니다.
데이터는 외부로 전송되지 않으며, 모델이 없어도 **stub 모드**로 즉시 개발과 테스트가 가능합니다.

## 1. 포함 파일
- `scripts/serving/butler_server_v1.py` : FastAPI 메인 서버
- `scripts/serving/model_pool_v1.py` : 모델 lazy-load, stub fallback, Qwen3 규칙 강제
- `scripts/serving/stream_handler_v1.py` : SSE 스트리밍
- `scripts/serving/auth_middleware_v1.py` : API key, allowlist, body size 제한
- `scripts/serving/server_config_v1.py` : 환경변수 기반 설정
- `scripts/serving/run_server_v1.sh` : 실행 스크립트
- `tests/serving/test_server_v1.py` : 단위 테스트

## 2. 빠른 시작 (stub 모드)
```bash
pip install fastapi uvicorn pydantic pytest httpx
export BUTLER_API_KEY_REQUIRED=false
uvicorn scripts.serving.butler_server_v1:app --port 8000
curl http://localhost:8000/healthz
```

## 3. 인증 사용 예시
```bash
export BUTLER_API_KEYS='your-api-key'
export BUTLER_API_KEY_REQUIRED=true
uvicorn scripts.serving.butler_server_v1:app --port 8000
```

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Authorization: Bearer your-api-key' \
  -H 'Content-Type: application/json' \
  -d '{
        "model":"butler-small",
        "messages":[{"role":"user","content":"안녕"}]
      }'
```

## 4. 스트리밍 예시
```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H 'Authorization: Bearer your-api-key' \
  -H 'Content-Type: application/json' \
  -d '{
        "model":"butler-small",
        "messages":[{"role":"user","content":"테스트"}],
        "stream":true
      }'
```

## 5. stub → 실제 모델 전환
- `output/butler_model_small_v1/adapter_model.safetensors` 가 존재하면 실제 모델 로드를 시도합니다.
- 실제 모델이 성공적으로 로드되면 `/health/readyz` 에서 `status=ready`, `loaded_models>0` 으로 표시됩니다.
- 어댑터가 없으면 예외로 죽지 않고 `stub` 로 남습니다.
- 어댑터는 있으나 Qwen3 템플릿 불일치나 패키지 문제로 로드에 실패하면 `503 not_ready` 로 fail-closed 됩니다.

## 6. 운영 원칙
- 외부 URL 호출 금지
- 응답 content 로깅 금지
- `usage` 는 실제 계산 전까지 모두 `-1`
- Qwen3 계열은 `enable_thinking=False` 강제
- `stream=true` 는 항상 `data: [DONE]` 으로 종료

## 7. 점검 엔드포인트
- `GET /healthz` : 프로세스 생존
- `GET /health/readyz` : 모델 준비 상태
- `GET /v1/models` : 버틀러 모델 목록
- `POST /v1/chat/completions` : 일반 / 스트리밍 채팅
- `GET /version` : 버전 정보
- `GET /metrics` : 요청/모델 수 메트릭

## 8. 트러블슈팅
- `401 authentication_required` : Authorization 헤더가 없습니다.
- `403 invalid_api_key` : API key 가 허용 목록에 없습니다.
- `404` : 존재하지 않는 모델 ID 입니다.
- `422` : 메시지 배열이 비었거나 파라미터 범위를 벗어났습니다.
- `503` : 실제 모델 연결 경로에서 fatal error 가 발생했습니다.

## 9. 테스트
```bash
python -m pytest tests/serving/test_server_v1.py -v
bash -n scripts/serving/run_server_v1.sh
```
