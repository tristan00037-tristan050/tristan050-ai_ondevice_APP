# Connect Loop Contract — SSOT v1.2

> **범위(PR-A)**: 데이터 계약(JSON Schema 4종) + 본 SSOT 문서 + 계약 검증 테스트 1개.
> 라우터 / 미들웨어 / UI 구현은 **이 PR에 포함하지 않는다.** 계약만 고정한다.
> 후속 PR(PR-B 이후)에서 라우터·미들웨어·UI가 본 계약을 준수해야 한다.

연결 루프(Connect Loop)는 다음 흐름을 단일 진실원천(SSOT)으로 고정한다.

```
사용자 입력
   │  (원문은 device-local 에만 존재)
   ▼
chat_request  ──►  router_decision  ──►  [실측 sidecar 엔드포인트 호출]
                                              │
                                              ▼
                                         usage_log (v1.1)   ← 감사·통계·후보탐색 (digest-only)
                                              │
                              (정책승인 + DLP + 보존기간 통과 시에만)
                                              ▼
                                         learning_event (v1) ← 학습 파이프라인 입력
```

---

## 1. 4종 계약 개요

| # | 계약 | 스키마 파일 | schema_version | 역할 |
|---|------|-------------|----------------|------|
| 1 | Chat Request | `schemas/connect_loop/chat_request.schema.json` | `chat_request.v1` | 사용자 입력이 라우터로 들어가기 직전의 계약. 원문은 담지 않고 digest/참조만. |
| 2 | Router Decision | `schemas/connect_loop/router_decision.schema.json` | `router_decision.v1` | intent 판정 + 대상 박스/엔드포인트 결정 결과. |
| 3 | Usage Log | `schemas/connect_loop/usage_log_v1_1.schema.json` | `usage_log.v1.1` | 요청 1건의 결과를 **감사·통계·후보탐색** 목적으로 남기는 digest-only 로그. |
| 4 | Learning Event | `schemas/connect_loop/learning_event_v1.schema.json` | `learning_event.v1` | 학습 파이프라인에 들어갈 수 있는 **유일한** 데이터 형태. 정제본/라벨/암호화참조만. |

모든 스키마는 **draft-07**, `additionalProperties: false`(unknown field **fail-closed**)이다.
모든 digest 필드는 `^sha256:[0-9a-f]{64}$` 형식(`sha256:` + 64 hex)을 강제한다. 이 형식은
sidecar 구현(`butler_pc_core/sidecar/routes/box2_rewrite.py`의 `digest_payload`)과 일치한다.

---

## 2. usage_log 와 learning_event 분리 원칙 (핵심)

> **digest는 학습 데이터가 아니라 감사·통계·후보 탐색 데이터다.**

- **usage_log (v1.1)** 는 모든 요청에 대해 남는 **감사/통계/후보탐색** 레코드다.
  - `retention_class` 는 `audit_digest_only` 로 **고정(const)** — 학습용 보존 분류가 아니다.
  - 원문은 어떤 필드에도 담기지 않는다. `external_send_zero=true`(const), `raw_text_logged=false`(const) 불변식으로 fail-closed 보장.
  - `learning_candidate=true` 라도 그것만으로 학습 데이터가 되지 않는다. 후보 탐색 신호일 뿐이다.

- **learning_event (v1)** 는 학습 파이프라인에 투입될 수 있는 **유일한** 형태다.
  - 생성 조건(아래 셋을 **모두** 통과해야 함, 미충족 시 스키마 단계에서 **BLOCK**):
    1. **정책 승인** — `policy_approval.decision` 존재 (승인 기록 없으면 BLOCK)
    2. **DLP 통과** — `dlp_result` 존재 (`passed/pii_detected/secret_detected/policy_violation`)
    3. **보존기간** — `retention_days` 존재 (+ `expires_at`)
  - 저장 가능한 것: **정제본의 digest/암호화 참조, 라벨**.
    - `approved_text_ref`(암호화 참조), `approved_text_digest`, `sanitized_summary_digest`, `label`.
  - **원문 저장 절대 금지 불변식**: `raw_input_saved=false`(const), `raw_output_saved=false`(const),
    `sanitized_summary_saved=false`(const) — 위반 시 BLOCK.
  - **APPROVED 상태 양성 강제(if/then)**: `status="APPROVED"` 이면 스키마가
    `policy_approval.decision="approved"` **및** `dlp_result.passed=true`(+ `pii_detected`/`secret_detected`/`policy_violation`=false)
    를 강제한다. 즉 미승인·DLP실패 데이터가 APPROVED 형태로 학습에 유입되는 것을 계약 수준에서 차단한다.
    (`CANDIDATE`/`REJECTED`/`EXPIRED` 는 검토 진행 중일 수 있으므로 이 제약을 적용하지 않는다.)
  - **자유 텍스트 밀반입 차단**: `reason_code` 류는 대문자 코드 패턴(`^[A-Z][A-Z0-9_]{0,63}$`),
    `approved_text_ref` 는 `scheme://...` 참조 형식(평문 금지)으로 제약한다.
  - `source_usage_log_id` 로 출처 usage_log를 역추적(감사) 가능.

**왜 분리하는가**: 감사/통계는 전수 보존이 필요하지만 학습은 정책·DLP·보존기간을 통과한 정제본만 허용해야
한다. 두 목적을 한 레코드에 섞으면 (a) 감사 로그가 학습 데이터로 오용되거나 (b) 미승인·미정제 데이터가
학습에 유입될 위험이 생긴다. 계약 수준에서 두 흐름을 분리하고 fail-closed 불변식으로 못박는다.

---

## 3. 실측 endpoint / 박스 매핑 (PR-A [0] 측정 결과)

아래 경로/박스 번호는 **추측이 아니라** 실제 코드에서 grep으로 확인한 값이다.
근거 코드: `butler_pc_core/sidecar/routes/*.py`, `butler_sidecar.py`, `butler_pc_core/prompts/cards/*.yaml`.

> **측정 기준(중요)**: 본 PR 의 베이스인 **`origin/main`** 기준으로 측정·검증했다(이 PR 워크트리에 그대로 존재).
> 일부 피처 브랜치/오래된 워크트리는 이 라우트들이 머지되기 **이전** 커밋일 수 있으니, 검증 시 반드시 PR 베이스에서 확인할 것.
> 재현:
> ```bash
> git ls-tree -r origin/main --name-only | grep sidecar/routes   # 라우트 파일 존재 확인
> grep -n "@router.post\|@app.post" butler_pc_core/sidecar/routes/*.py butler_sidecar.py
> ```
> 계약 테스트 `test_router_endpoint_paths_exist_in_sidecar_source` 가 이 표의 각 경로가 소스에 실재하는지 자동 grep 한다(토톨로지 방지).

| intent_label | 박스/헬퍼 (`target_box_id` / `box_id`) | 기능 | 실측 엔드포인트 (`target_endpoint` / `endpoint`) | 근거 (file:line) |
|--------------|------------------------|------|--------------------------------------------------|------------------|
| `memory_search` | `helper1` | 메모리/기억 검색 (helper1) | `POST /v1/helpers/1/search` | `sidecar/routes/helper1_search.py:111` (보조: `:159` `POST /v1/helpers/1/ask`) |
| `form_convert` | `2` | 양식 변환 (외부→우리 양식) | `POST /v1/cards/2/rewrite` | `sidecar/routes/box2_rewrite.py:52` |
| `draft_write` | `3` | 새 초안 작성 (과거기반) | `POST /v1/cards/3/draft` | `sidecar/routes/box3_draft.py:45` |
| `accounting_classify` | `5` | **회계 분류 (은행→회계)** | `POST /accounting/classify` | `butler_sidecar.py:977` |
| `general_chat` | `chat` | 일반 대화 (OpenAI 호환) | `POST /v1/chat/completions` | `sidecar/routes/chat_completions.py:93` (보조: `scripts/serving/butler_server_v1.py:122`) |
| `unknown` | `none` | 미상 → fallback | `none` (엔드포인트 미지정, `fallback_required=true`) | — |

### 카드 ↔ 박스 ↔ 기능 정의 (근거: `butler_pc_core/prompts/cards/`)

| 카드 정의 파일 | 박스 번호 | 기능 | 연결 루프 intent |
|----------------|-----------|------|------------------|
| `card_01_request_parse.yaml` | 1 | 요청 파싱 | (연결 루프 외) |
| `card_02_external_to_our_format.yaml` | **2** | 외부→우리 양식 변환 | `form_convert` |
| `card_03_new_draft_from_past.yaml` | **3** | 과거 기반 새 초안 | `draft_write` |
| `card_04_document_review.yaml` | 4 | 문서 검토 | (연결 루프 외) |
| `card_05_bank_to_accounting.yaml` | **5** | **은행→회계 분류** | `accounting_classify` |
| `card_06_fill_external_form.yaml` | 6 | 외부 양식 채우기 | (연결 루프 외) |

> **회계분류는 박스 4가 아니라 박스 5다** (`card_05_bank_to_accounting`). 실측으로 확정.
> 회계분류 엔드포인트는 `/v1/cards/5/...` 형태가 **아니라** `POST /accounting/classify`(SSE, multipart/form-data) 이다.
> 코드에 없는 경로(`/v1/cards/4/*`, `/v1/cards/5/*`, `/boxes/*` 등)는 어떤 enum에도 적지 않았다.

### 라우터 등록 현황 (참고)

`butler_sidecar.py:294-300` 에서 `box2_rewrite`, `box3_draft`, `helper1_search` 라우터가 `include_router` 로
등록된다. `accounting/classify` 와 `request_parsing/*`, `document_transform/*` 는 `butler_sidecar.py` 에
`@app.post` 로 직접 정의되어 있다. `chat_completions` 라우터(`/v1/chat/completions`)는 모듈로 존재하며
서빙 서버(`scripts/serving/butler_server_v1.py`)에서도 동일 경로로 제공된다.

---

## 4. 금지 필드 (전 계약 공통, fail-closed)

`additionalProperties: false` 에 의해 정의되지 않은 모든 필드는 거부된다. 특히 아래 원문/비밀 계열은
어떤 계약에도 등장해서는 안 된다 (테스트로 검증):

```
raw_text, raw_query, raw_answer, raw_source_text,
source_doc_name(원문), file_name(원문), absolute_local_path,
token, password, secret
```

대신 사용하는 안전 대체:
- 원문 텍스트 → `text_ref="device_local_only"` + `text_digest`(sha256)
- 소스/첨부 → `source_digests[]` / `attachments[].content_digest` (sha256)
- 식별자 → `*_id_digest` (sha256)

> **`device_id` carve-out (의도적)**: `chat_request.device_id` 만 digest 가 아닌 원시 식별자다.
> 디바이스 식별자는 PII 가 아닌 안정적 기기 ID(디바이스-로컬 라우팅/디버깅에 필요)이며, 감사 로그로 넘어갈 때는
> `usage_log.device_id_digest` 로 digest 화된다. 즉 **원시 device_id 는 device-local 경계 안에서만 쓰이고,
> 경계를 넘는 usage_log/learning_event 에는 digest 만 남는다.**

---

## 5. 계약 검증 테스트

`tests/connect_loop/test_schema_contract.py` (pytest + jsonschema, draft-07) 가 다음을 강제한다:

1. 4개 스키마 self-validate (draft-07 meta) 통과 + `additionalProperties:false` 확인
2. 유효 샘플 4건 validate 통과
3. 금지 필드(raw_text 등 10종) 포함 시 fail (fail-closed)
4. sha256 digest 형식 위반 시 fail / 정상 형식 통과
5. required 필드 누락 시 fail (모든 required 필드 개별 검증)
6. learning_event: `policy_approval` / `policy_approval.decision` / `dlp_result` / `retention_days` 없으면 BLOCK,
   `raw_input_saved`/`raw_output_saved`/`sanitized_summary_saved` = true 면 BLOCK
7. learning_event: `status="APPROVED"` 인데 `policy_approval.decision≠approved` 또는 `dlp_result.passed≠true`
   (또는 PII/secret/위반 검출) 이면 BLOCK; `CANDIDATE` 는 미완료 상태 허용
8. usage_log: `external_send_zero`/`raw_text_logged`/`retention_class` const 위반 시 fail
9. const 위반(`schema_version`, `text_ref`) / enum 위반 / 수치 경계(`routing_confidence` 0..1, `retention_days`≥1) 위반 시 fail
10. RFC3339 date-time pattern 위반 시 fail (`format` 미검증 환경 대비 pattern 강제)
11. `reason_code` 류 자유 원문 / `approved_text_ref` 비참조 평문 시 fail (밀반입 채널 차단)
12. router_decision `target_endpoint` enum 이 §3 실측 경로 집합과 일치하고, **각 경로가 실제 sidecar 소스에 존재**하는지 grep 확인(토톨로지 방지)

테스트 총 136건 통과.

실행:

```bash
python -m pytest tests/connect_loop/test_schema_contract.py -v
```

---

## 6. 버전 / 변경 정책

- 본 문서는 v1.2. 스키마는 각각 자체 `schema_version`(const)을 가진다.
- 계약 변경 시: (a) 본 SSOT 갱신 → (b) 스키마 `schema_version` bump → (c) 테스트 갱신 을 한 PR에서 함께 한다.
- `usage_log.schema_hash` 는 사용된 스키마 본문 digest로, 런타임에서 계약 드리프트를 감지하는 데 쓴다(후속 PR).
