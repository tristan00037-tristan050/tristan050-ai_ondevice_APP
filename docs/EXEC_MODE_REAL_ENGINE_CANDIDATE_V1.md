# Exec Mode V1 — 실엔진 후보 확정 (1회)

확정 일자: 2026-02-26  
확정 절차: `git grep` / `find` / 스크립트 내부 검토 + 1회 실행 여부.

---

## 1) 실엔진 후보 1개 이름/경로

### 탐색 결과 요약

| 우선순위 | 위치 | 결과 |
|----------|------|------|
| tools/, scripts/, apps/ | `tools/exec_mode/run_exec_mode_v1.sh` (mock만 지원), `scripts/verify/verify_ondevice_*.sh` | prompt → result 텍스트를 주는 단일 실행 엔트리 없음 |
| Dockerfile*, compose*, .github/workflows | exec_mode는 `--engine mock`만 CI에서 사용 | 실엔진 엔트리 미참조 |
| README*, docs/* | R9S2 등에서 llama.cpp/onnx 연동 “별도 스프린트” 명시 | 현재 구현 없음 |

### 확정: 실엔진 “실행 엔트리” 후보 (2개, P3는 real-compute 우선)

**후보 A — 실연산 경로 (P3 연동 권장):**  
**`scripts/verify/verify_ondevice_real_compute_once.sh`**

- **역할:** 온디바이스 **실연산 1회** 검증. 모델팩 검증 후 **실제 연산**(입력 JSON → sha256) 수행, `ONDEVICE_EXEC_MARKER`에 **result_fingerprint_sha256** 포함.
- **특징:** meta-only가 아닌 **실제 연산 수행** + 결과 지문 산출 → 실험 유효성·엔진 연동에 적합.
- **한계:** prompt 입력을 받지 않고, 텍스트 완성(result)을 출력하지 않음. P3 어댑터에서 입력/출력 매핑 필요.

**후보 B — 메타/계약 경로:**  
**`scripts/verify/verify_ondevice_model_exec_v0.sh`**

- **역할:** 온디바이스 모델 실행 **계약** 검증(모델팩 로드 + 서명/만료 + 4케이스 A/B/C/D).  
- **한계:** “실제 연산”은 **meta-only 3블록 생성**으로 대체됨. 코드 주석: `TODO: 실제 모델 실행 (모델 파일 + 실행 엔진 + 입력 → 결과)` (후속 PR 예정). **result_fingerprint_sha256 미산출.**

**결론:**  
실엔진으로 **지정**할 수 있는 실행 엔트리는 위 **2개**.  
**P3 연동 시** 실연산·결과 지문이 있는 **후보 A(verify_ondevice_real_compute_once.sh)** 를 우선 사용하고, 어댑터는 “입력: prompts JSONL → 출력: result.jsonl” 형태로 이 경로(또는 butler-runtime)에 연결할 것. 후보 B는 계약/메타 검증용으로 유지.

---

## 2) 실행 커맨드 확정 (입력 전달 + 출력 수집 + 실패 신호)

**대상 (P3 권장):** `scripts/verify/verify_ondevice_real_compute_once.sh` (인자 없이 실행).

| 항목 | 내용 |
|------|------|
| **입력 전달** | prompt/파일 미지원. 스크립트 내부에서 고정 경로 사용: `model_packs/accounting_v0`, `model_packs/_bad_*`. **prompt.jsonl 인터페이스 없음.** |
| **출력 수집** | 임시 `EXEC_OUTPUT`(exec_output.json)에 **result_fingerprint_sha256** 포함 마커(JSON) 기록. stdout에 `ONDEVICE_EXEC_MARKER {...}`, `ONDEVICE_REAL_COMPUTE_ONCE_OK=1` 등. **result.jsonl 형태의 텍스트 완성 결과 없음.** |
| **실패 신호** | `exit 1`, stdout/stderr에 `BLOCK: ...` 포함. |

**참고 (후보 B):** `verify_ondevice_model_exec_v0.sh` — 동일하게 고정 pack 경로, 출력은 meta 마커(result_fingerprint_sha256 없음), 실패 시 `BLOCK: ondevice exec verify failed` 등.

**P2 러너와의 관계:**  
`tools/exec_mode/run_exec_mode_v1.sh`는 `--engine mock`만 지원.  
P3에서는 **실연산 경로(verify_ondevice_real_compute_once.sh)** 를 우선 **어댑터**로 감싸 “입력: prompts JSONL → 출력: result.jsonl”로 연결할 것.

---

## 3) tokens_out 산출 가능 여부

- **확인 방법:** 실엔진 후보(`verify_ondevice_model_exec_v0.sh`) 1회 실행 및 출력/로그 검사.  
- **실행:**  
  - `bash scripts/verify/verify_ondevice_model_exec_v0.sh` (필요 시 Node 18+, model_packs 존재).  
  - stdout/EXEC_OUTPUT에는 `request_id`, `compute_path`, `pack_id`, `latency_ms`, `backend` 등 **meta 필드만** 존재.  
- **grep 결과:**  
  - `scripts/verify/` 내 ondevice 관련 스크립트에서 `token`, `tokens`, `tok/s`, `output_tokens`, `completion_tokens` **0건**.

**확정:**  
- **tokens_out 산출: 불가.**  
- P3 스키마에서는 **tokens_out=null** 고정, **engine_meta.tokens_out_supported=false** 로 명시할 것.

---

## 결론: 대표님 확정 절차 한 줄 요약

- **git grep / find**로 실엔진 엔트리 **2개**를 확정: **실연산 경로** `scripts/verify/verify_ondevice_real_compute_once.sh`(result_fingerprint_sha256 산출), **계약 경로** `scripts/verify/verify_ondevice_model_exec_v0.sh`(meta-only, TODO).  
- **P3 연동은 실연산 경로(real_compute_once)를 우선** 사용해 실험 유효성·엔진 통합을 확보.  
- 입력=고정 pack 경로, 출력=exec_output.json(실연산 경로는 result_fingerprint_sha256 포함), 실패=exit 1 + BLOCK.  
- **tokens_out** 은 **불가** → P3 스키마에서 **tokens_out=null**, **tokens_out_supported=false**.

P3에서는 **실연산 엔트리(verify_ondevice_real_compute_once.sh)** 또는 butler-runtime을 사용하는 어댑터를 추가해, `run_exec_mode_v1.sh --engine ondevice` 가 prompts JSONL → result.jsonl 을 생성하도록 연결합니다.
