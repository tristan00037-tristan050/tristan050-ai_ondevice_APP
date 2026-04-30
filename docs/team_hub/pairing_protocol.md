# Butler PC Core ↔ Team Hub 페어링 프로토콜

**버전**: 1.0.0  
**작성일**: 2026-04-30  
**상태**: Draft (Day 1)

---

## 1. 개요

Butler PC Core(이하 **PC Core**)와 Team Hub 서버(이하 **Hub**) 간의 통신 규격을 정의한다.  
전송 계층은 **JSON-RPC 2.0** over HTTP(S) / WebSocket 이중 지원.  
모든 민감 데이터(금융·개인정보)는 PC Core 로컬에서만 처리하며 Hub로 원문을 전송하지 않는다.

---

## 2. 전송 계층

| 항목 | 값 |
|------|-----|
| 기본 프로토콜 | HTTPS (TLS 1.3 이상) |
| 폴백 | WebSocket (`wss://`) |
| 포트 (Hub) | `7443` (HTTPS) / `7444` (WSS) |
| 포트 (PC Core Sidecar) | `8765` |
| 인코딩 | UTF-8 |
| 최대 메시지 크기 | 64 KB (페어링 제어 메시지 한도) |

---

## 3. JSON-RPC 기본 형식

### 3.1 요청 (Request)

```json
{
  "jsonrpc": "2.0",
  "id": "<string | integer>",
  "method": "<namespace>.<method>",
  "params": { }
}
```

### 3.2 성공 응답 (Result)

```json
{
  "jsonrpc": "2.0",
  "id": "<동일 id>",
  "result": { }
}
```

### 3.3 오류 응답 (Error)

```json
{
  "jsonrpc": "2.0",
  "id": "<동일 id | null>",
  "error": {
    "code": -32000,
    "message": "오류 설명",
    "data": { }
  }
}
```

#### 오류 코드 표

| 코드 | 의미 |
|------|------|
| -32700 | Parse error |
| -32600 | Invalid Request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |
| -32001 | 인증 실패 (pairing token mismatch) |
| -32002 | 작업 용량 초과 (XL tier blocked) |
| -32003 | Hub 오프라인 |
| -32004 | PC Core 오프라인 |
| -32005 | 페어링 만료 |

---

## 4. 페어링 흐름

```
PC Core Sidecar                    Team Hub
      │                                │
      │── pairing.request ────────────▶│
      │                                │  (토큰 검증)
      │◀─ pairing.challenge ───────────│
      │                                │
      │── pairing.verify ─────────────▶│
      │                                │  (세션 생성)
      │◀─ pairing.established ─────────│
      │                                │
      │    (이후 작업 위임 가능)         │
```

### 4.1 `pairing.request`

PC Core → Hub. 페어링 시작 요청.

**params**

```json
{
  "client_id":   "pc-core-<uuid4>",
  "version":     "0.9.0",
  "public_key":  "<Base64 X25519 공개키>",
  "capabilities": ["task_delegate", "partial_result_push", "precheck"]
}
```

**result**

```json
{
  "challenge": "<32바이트 랜덤 hex>",
  "hub_id":    "hub-<uuid4>",
  "expires_in": 30
}
```

---

### 4.2 `pairing.challenge`

Hub → PC Core. challenge 발급 (Server-Push / WebSocket Notify 허용).

> HTTP 모드에서는 `pairing.request` result에 포함.

---

### 4.3 `pairing.verify`

PC Core → Hub. challenge에 서명하여 신원 증명.

**params**

```json
{
  "client_id":  "pc-core-<uuid4>",
  "challenge":  "<challenge hex>",
  "signature":  "<Ed25519 서명, Base64>",
  "device_name": "홍길동-MacBookPro"
}
```

**result**

```json
{
  "session_token": "<JWT or opaque token>",
  "session_id":    "<uuid4>",
  "expires_at":    "2026-04-30T23:59:59Z",
  "hub_version":   "2.1.0"
}
```

---

### 4.4 `pairing.established`

Hub → PC Core (WebSocket Notify 또는 응답 완료 신호).

```json
{
  "jsonrpc": "2.0",
  "method": "pairing.established",
  "params": {
    "session_id": "<uuid4>",
    "paired_at":  "2026-04-30T09:00:00Z"
  }
}
```

---

## 5. 작업 위임 메서드

### 5.1 `task.delegate`

XL tier 파일 등 PC Core 처리 불가 작업을 Hub에 위임.

**params**

```json
{
  "session_token": "<session_token>",
  "task_id":       "<uuid4>",
  "card_id":       "card_02_external_to_our_format",
  "tier":          "XL",
  "file_meta": {
    "name":     "large_contract.pdf",
    "size_kb":  2048,
    "checksum": "<sha256>"
  },
  "input_summary": "외부 계약서 → 우리 양식 변환 요청",
  "callback_url":  "http://127.0.0.1:8765/api/task_callback"
}
```

**result**

```json
{
  "accepted":    true,
  "hub_task_id": "<hub-uuid4>",
  "eta_seconds": 120
}
```

---

### 5.2 `task.status`

위임된 작업 진행 상태 조회.

**params**

```json
{
  "session_token": "<session_token>",
  "hub_task_id":   "<hub-uuid4>"
}
```

**result**

```json
{
  "hub_task_id": "<hub-uuid4>",
  "status":      "processing",
  "progress_pct": 45,
  "eta_seconds":  60
}
```

`status` 값: `queued` | `processing` | `completed` | `failed` | `cancelled`

---

### 5.3 `task.cancel`

진행 중 작업 취소 요청.

**params**

```json
{
  "session_token": "<session_token>",
  "hub_task_id":   "<hub-uuid4>"
}
```

**result**

```json
{
  "cancelled": true,
  "partial_result_available": true
}
```

---

## 6. Partial Result 콜백

Hub가 PC Core 사이드카의 `/api/task_callback`으로 결과를 Push.

```json
{
  "jsonrpc": "2.0",
  "method":  "task.result_ready",
  "params": {
    "hub_task_id":   "<hub-uuid4>",
    "task_id":       "<원본 task_id>",
    "status":        "completed",
    "partial":       false,
    "result_url":    "https://hub/results/<hub-uuid4>",
    "checksum":      "<sha256>"
  }
}
```

> **보안**: result_url은 1회용 서명 URL (15분 유효). 원문 데이터는 URL 응답에만 포함.

---

## 7. 세션 갱신 / 해제

### `pairing.refresh`

```json
{ "session_token": "<현재 토큰>" }
```

**result**: 새 `session_token` + `expires_at`

### `pairing.disconnect`

```json
{ "session_token": "<현재 토큰>", "reason": "user_logout" }
```

**result**: `{ "disconnected": true }`

---

## 8. 보안 요구사항

| 항목 | 요구사항 |
|------|---------|
| 전송 암호화 | TLS 1.3 필수 |
| 인증 | Ed25519 서명 + JWT Bearer |
| 토큰 유효기간 | 최대 24시간 (갱신 가능) |
| 민감 데이터 | PC Core 로컬에서만 처리, Hub 전송 금지 |
| 로그 | session_token / signature 평문 로그 금지 |
| 재전송 공격 방지 | challenge는 1회 사용 후 즉시 무효화 |

---

## 9. 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| 1.0.0 | 2026-04-30 | 최초 Draft (Day 1) |
