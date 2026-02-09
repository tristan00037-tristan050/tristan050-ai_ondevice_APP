# P0 Launcher Requirements v1 (SSOT)

## 목표
대표님이 "눈으로 확인" 가능한 체감물 고정

## P0-1. Launcher 메인 화면

### 필수 요소

#### A) 입력창 + 버튼
- 입력창 1개: 검색/질문 입력
- 버튼 2개:
  - 실행 (Execute)
  - 취소 (Abort)

#### B) 결과 영역 (3블록 카드)
- "핵심" 카드
- "결정" 카드
- "다음행동" 카드

#### C) 하단 meta-only 패널 (필수 8개)
없으면 N/A로 표시:
1. `request_id`
2. `compute_path`
3. `pack_id/version/manifest_sha256`
4. `latency_ms`
5. `peak_mem_mb`
6. `result_fingerprint_sha256`
7. `reason_code_v1`
8. `egress_attempt_blocked`

### 금지 사항
- 원문/프롬프트/출력 텍스트를 저장하거나 로그로 남김
- Logs에도 meta-only만 저장

## P0-2. Settings 화면

### 필수 설정

#### Gateway URL
- 기본값: `http://127.0.0.1:8081`
- 사용자가 변경 가능

#### Health 버튼
- `/healthz` 호출
- 응답에서 `build_sha` 표시

#### Live 모드 필수 헤더
- `X-Tenant`
- `X-User-Id`
- `X-User-Role`

**Fail-closed 규칙:**
- Live 모드에서 헤더가 비어있으면 전송 전에 차단 (네트워크 전송 0)

## P0-3. Quick Eval 기능

### 고정 입력 10개
- 코드에 박기 (자동 실행용)
- 입력은 meta-only 형태로 구성
- 짧은 테스트 문자열 10개 정도는 UI에서만 사용, 저장은 meta-only만

### 실행 방식
1. 10개를 1회 실행
2. 같은 10개를 다시 1회 실행 (총 2회)

### 화면 출력 (필수)
- 성공률 (예: 20회 중 성공 몇 회)
- 지연 p50 / p95 (ms)
- fingerprint 일관성
  - 같은 입력의 1회차와 2회차 `result_fingerprint_sha256`가 같은지 (같으면 OK)

### 저장 방식 (필수)
- JSONL (meta-only)로 로컬 저장 (localStorage)
- 저장 필드 예시 (텍스트 본문 저장 금지):
  - `timestamp`
  - `request_id`
  - `compute_path`
  - `latency_ms`
  - `peak_mem_mb`
  - `result_fingerprint_sha256`
  - `reason_code_v1`
  - `pack meta` (pack_id, version, manifest_sha256)

## P0-4. 완료 판정 기준

### UI에서 눈으로 확인
1. 검색창에서 실행하면 결과 3블록이 보임
2. 하단 meta-only 패널 8개가 채워짐 (없으면 N/A)
3. Logs에 meta-only 이력만 쌓임

### Quick Eval에서 숫자가 나온다
1. 성공률, p50/p95, 일관성 결과가 나온다
2. 저장(JSONL)이 로컬에 남는다

## API 엔드포인트

### Gateway 엔드포인트
- 기본 URL: `http://127.0.0.1:8081`
- Health: `GET /healthz` → `build_sha` 반환
- Algo Core: `POST /v1/os/algo/three-blocks`
  - 요청: meta-only JSON
  - 응답: 3 blocks + manifest SHA256 + signature

### Live 모드 필수 헤더
```
X-Tenant: <tenant_id>
X-User-Id: <user_id>
X-User-Role: <user_role>
```

## Meta-Only 저장 규칙

### 허용 필드
- `request_id`
- `compute_path`
- `pack_id`, `pack_version`, `manifest_sha256`
- `latency_ms`
- `peak_mem_mb`
- `result_fingerprint_sha256`
- `reason_code_v1`
- `egress_attempt_blocked`
- `timestamp`

### 금지 필드
- `prompt`
- `raw_text`
- `messages`
- `content`
- `output_text`
- `input_text`
- 기타 원문/프롬프트/출력 텍스트

