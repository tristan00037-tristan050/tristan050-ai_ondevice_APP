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

### 확정: 실엔진 “실행 엔트리” 1개

**지정 엔트리:**  
**`scripts/verify/verify_ondevice_model_exec_v0.sh`**

- **역할:** 온디바이스 모델 실행 경로 검증(모델팩 로드 + meta-only 실행 + 서명/만료 검증).  
- **한계:** prompt 입력을 받지 않고, 텍스트 완성(result)을 출력하지 않음.  
  - 내부: 임시 Node 스크립트 생성 → `webcore_appcore_starter_4_17/packages/butler-runtime/src/model_pack/apply_model_pack.mjs` 사용, “실제 연산”은 **meta-only 3블록 생성**으로 대체됨.  
  - 코드 주석: `TODO: 실제 모델 실행 (모델 파일 + 실행 엔진 + 입력 → 결과)` (후속 PR에서 추가 예정).

**결론:**  
“이 파일이 실엔진이다”라고 **지정**할 수 있는 실행 엔트리는 **이 스크립트 1개**로 확정.  
다만 현재 이 엔트리는 **prompt → result.jsonl** 형태의 exec_mode 러너와 직접 연결되지 않으며, P3에서 **어댑터**(입력: prompts JSONL, 출력: result JSONL)를 이 경로 또는 butler-runtime 쪽에 추가해야 함.

---

## 2) 실행 커맨드 확정 (입력 전달 + 출력 수집 + 실패 신호)

대상: `scripts/verify/verify_ondevice_model_exec_v0.sh` (인자 없이 실행).

| 항목 | 내용 |
|------|------|
| **입력 전달** | prompt/파일 미지원. 스크립트 내부에서 고정 경로 사용: `model_packs/accounting_v0`, `model_packs/_bad_*`. 즉, **prompt.jsonl을 넘기는 인터페이스 없음.** |
| **출력 수집** | 스크립트가 임시 디렉터리 `EXEC_OUTPUT`(exec_output.json)에 meta 마커(JSON) 기록. stdout에는 `ONDEVICE_EXEC_MARKER {...}`, `ONDEVICE_MODEL_EXEC_V0_OK=1` 등 문자열 출력. **result.jsonl 형태의 텍스트 완성 결과 없음.** |
| **실패 신호** | `exit 1`, stdout/stderr에 `BLOCK: ...` 포함. 예: `BLOCK: ondevice exec verify failed`, `BLOCK: missing ONDEVICE_EXEC_MARKER`. |

**P2 러너와의 관계:**  
`tools/exec_mode/run_exec_mode_v1.sh`는 `--engine mock`만 지원하며, 엔진별 어댑터 호출 구조(예: `engines/ondevice_runtime_v1.sh` 등)는 아직 없음.  
P3에서 위 실엔진(또는 butler-runtime 진입점)을 **어댑터**로 감싸서 “입력: prompts JSONL → 출력: result.jsonl”로 맞추는 작업이 필요.

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

- **git grep / find**로 실엔진 엔트리 1개를 **`scripts/verify/verify_ondevice_model_exec_v0.sh`** 로 확정했고,  
- 해당 엔트리는 **입력=고정 pack 경로, 출력=meta 마커(exec_output.json/stdout), 실패=exit 1 + BLOCK 메시지**이며,  
- **1회 실행**으로 **tokens_out** 은 제공되지 않아 **불가**로 확정했으며, P3에서 **tokens_out=null**, **tokens_out_supported=false** 로 설계합니다.

P3에서는 위 엔트리(또는 butler-runtime)를 사용하는 **어댑터**를 추가해, `run_exec_mode_v1.sh --engine ondevice` 가 prompts JSONL → result.jsonl 을 생성하도록 연결하면 됩니다.
