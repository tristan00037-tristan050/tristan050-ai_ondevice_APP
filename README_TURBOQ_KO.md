# Butler TurboQuant 통합 번들 (AI-21)

## 1. 목적
이 번들은 업로드된 합본 개발 지시서(v3.0)를 기준으로, **TurboQuant(논문-정합 구현) KV 캐시 압축**을 버틀러 서버/모바일 온디바이스 경로에 연결하기 위한 알고리즘팀 범위 산출물을 제공합니다.

중요 원칙:
- **공식 Google 코드와 동일하다고 주장하지 않습니다.** 공식 코드는 2026-03-27 기준 공개되지 않았습니다.
- 논문/블로그의 6x 압축, 8x 속도 향상은 **목표치**이며, 버틀러 실측 전에는 제품 성능으로 주장하지 않습니다.
- 압축 실패 시 무응답/오류 종료 대신 **원본 KV 캐시 경로로 폴백**합니다.
- 실측 없는 가짜 benchmark JSON, placeholder measured_* 값, 가짜 ONNX/MNN 산출물은 만들지 않습니다.

## 2. 포함 파일
- `scripts/turboq/turboq_core_v1.py`
- `scripts/turboq/turboq_butler_hook_v1.py`
- `scripts/turboq/turboq_server_v1.py`
- `scripts/turboq/turboq_mobile_v1.py`
- `scripts/turboq/turboq_benchmark_v1.py`
- `scripts/turboq/turboq_verify_v1.py`
- `scripts/turboq/turboq_run_dryrun_v1.sh`
- `tests/turboq/test_turboq_core.py`
- `tests/turboq/test_turboq_hook.py`
- `BENCHMARK_TURBOQ_KO.md`
- `STATUS_WEEKLY_KO.md`

## 3. 구현 개요
### 3-1. `turboq_core_v1.py`
- `LloydMaxQuantizer`: 표준정규 분포 근사 좌표에 대해 동작하는 scalar quantizer
- `PolarQuant`: 직교 회전(QR) + Lloyd-Max 양자화
- `QJLCorrector`: 1-bit residual sign sketch 기반 편향 보정용 스캐폴드
- `TurboQuantKVCache`: KV 캐시 압축/요약 인터페이스

### 3-2. `turboq_butler_hook_v1.py`
- 기본 모드는 `wrapper`
- `forward` 직접 교체 대신 wrapper로 안전하게 연결
- 실패 조건: `compressor_missing`, `unsupported_cache_shape`, `runtime_error`
- 실패 시 원본 KV 캐시 반환

### 3-3. `turboq_server_v1.py`
- `/v1/turboq/status` 제공
- `/v1/chat/completions` 계약 변경 없음
- 실제 서빙 핸들러 연결은 메인개발팀 범위

### 3-4. `turboq_mobile_v1.py`
- 가용 RAM 기반 bits heuristic
- MNN/llm_demo 연결 계획
- 실제 MNN 삽입/실기기 측정은 실행팀 범위

### 3-5. `turboq_benchmark_v1.py`
- dry-run은 `expected_*`만 생성
- GPU 측정 경로는 injected measurement function 필요

### 3-6. `turboq_verify_v1.py`
- 파일 구조 확인
- Lloyd-Max MSE 확인
- normalized vector 기반 inner-product bias CPU smoke test
- GPU/실기기 항목은 `skipped_checks`로 남김

## 4. 로컬 dry-run 실행
```bash
cd /path/to/butler_turboq_ai21_bundle
bash scripts/turboq/turboq_run_dryrun_v1.sh
```

생성되는 주요 파일:
- `tmp/turboq_compile_result.txt`
- `tmp/turboq_verify_result.json`
- `tmp/turboq_unittest_result.txt`
- `tmp/turboq_shell_syntax_result.txt`

## 5. 실제 검증이 아직 필요한 항목
아래는 **이번 번들로 지금 즉시 학습/검증할 수 없고**, 실행팀 또는 메인개발팀이 후속으로 수행해야 하는 항목입니다.

1. GPU 서버에서의 실제 KV 메모리 절감 실측
2. 장기 문맥 정확도(예: 8K/16K/32K) 실측
3. 버틀러 OpenAI 호환 서빙 통합테스트
4. Android/iOS 실기기 MNN 경로 smoke/thermal/latency 측정
5. TurboQuant가 실제 버틀러 모델/프롬프트/업무시나리오에 미치는 체감 품질 평가

## 6. 설계상 주의점
- Qwen3-4B 공식 config 기준 `num_hidden_layers=36`, `num_attention_heads=32`, `num_key_value_heads=8`, `head_dim=128`입니다.
- 업로드된 지시서 예시에 있는 `num_heads=16`은 공식 값과 다르므로, hook는 모델 config가 있으면 그것을 우선 사용합니다.
- 본 번들의 `QJLCorrector`는 CPU dry-run 재현성을 우선한 deterministic scaffold입니다. 공식 Google 코드가 공개되면 estimator/packing을 재검토해야 합니다.

## 7. 권장 다음 단계
1. 메인개발팀: 실제 버틀러 모델 로더/서빙 라우터에 wrapper 연결
2. 실행팀: GPU 벤치마크 및 `tmp/turboq_benchmark_result.json` 실측 생성
3. 실행팀: MNN 실기기 smoke/latency/thermal 측정
4. 알고리즘팀: 실측 결과 기반으로 bits/QJL sketch length/폴백 정책 재튜닝
