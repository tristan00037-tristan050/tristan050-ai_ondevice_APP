# AI On-device Enterprise Playbook

## 모델 아티팩트 경로 표준 (WebLLM)

### 1) 원칙
- 모델 아티팩트(모델 파일)는 외부 도메인에서 직접 fetch하지 않는다.
- 허용 경로는 다음 둘 중 하나로 제한한다.
  - 동일 오리진(현재 웹 도메인)
  - BFF 프록시 경로

### 2) BFF 프록시 사용 강제
- WebLLM 모델 아티팩트 요청은 반드시 아래 경로를 통해서만 수행한다.
  - `GET/HEAD /v1/os/models/:modelId/*path`
- 클라이언트(WebLLMAdapter)는 모델 base URL을 검증하고, 동일 오리진 또는 BFF가 아니면 fail-closed로 차단한다.
- BFF 프록시는 SSRF/Traversal 방지를 위해 다음을 적용한다.
  - 업스트림은 `WEBLLM_UPSTREAM_BASE_URL` 하나로만 고정 (임의 URL 파라미터 금지)
  - `WEBLLM_ALLOWED_MODEL_IDS` allowlist 적용
  - path traversal(`..` 및 인코딩된 `..`) 차단
  - 확장자 allowlist(json/bin/wasm/params/txt 등) 적용

### 3) 팀 공용 정적호스트(업스트림) 표준 (NCP VPC-Nginx)
- 팀 공용 업스트림은 아래 형태로 제공한다. (끝 `/` 포함)
  - `WEBLLM_UPSTREAM_BASE_URL="https://<사내-정적호스트>/webllm/"`
- 업스트림 파일 구조는 아래로 고정한다.
  - `https://<사내-정적호스트>/webllm/<modelId>/<files...>`
- dev_check 자동검증이 절대 깨지지 않도록, 모든 모델 폴더에 아래 파일을 반드시 포함한다.
  - `<modelId>/manifest.json` (작은 JSON probe 파일)

### 4) 캐시 정책 표준
- 표준 정책(B안, P0 안전책): ETag + 304 기반 재검증
  - `Cache-Control: public, max-age=86400`
  - `ETag` 제공 및 `If-None-Match`에 대해 `304 Not Modified` 동작
  - `Content-Length` 제공(가능하면 항상)
- immutable 정책은 “URL 버저닝(버전/해시 경로 포함)”이 확정된 경우에만 허용한다.
  - 예: `/webllm/<modelId>/<artifactSha>/...` 형태일 때만 `immutable` 적용 가능

### 5) 표준 검증(dev_check)
- dev_check는 아래 3개 변수만으로 모델 프록시/캐시/보안 검증이 가능해야 한다.
  - `WEBLLM_TEST_MODEL_ID` (예: local-llm-v1)
  - `WEBLLM_TEST_MODEL_FILE` (예: manifest.json)
  - `WEBLLM_UPSTREAM_BASE_URL` (팀 공용 업스트림)
- dev_check는 다음 항목을 자동 PASS/FAIL로 강제한다.
  - 프록시 HEAD 200 + ETag/Cache-Control/Content-Length 존재
  - If-None-Match 재요청 시 304(또는 정책에 따른 허용 코드)
  - unknown modelId → 403, traversal → 400, 금지 확장자 → 400
