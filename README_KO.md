# AI-20 | butler_model_small_v1 (Qwen3-4B) 학습 파이프라인 번들

본 번들은 **알고리즘 개발팀6(온디바이스)** 가 AI-20 지시서 기준으로 바로 레포지토리에 반영할 수 있도록 정리한 드롭인(drop-in) 산출물입니다.

## 1. 범위와 책임 분리

**알고리즘팀 DoD**
- 코드 파이프라인 완성
- 맥북/PC 기준 dry-run 통과
- pytest 통과
- PR 제출 가능 상태 확인

**알고리즘팀 DoD에 포함되지 않음**
- 실제 GPU 학습 실행
- `adapter_model.safetensors` 실제 생성
- Phase C 실측 통과
- SSD 저장 및 서버 반납

## 2. 번들 포함 파일

필수 파일
- `scripts/cloud/apply_small_overlay_v1.py`
- `scripts/cloud/run_training_small_v1.sh`
- `scripts/cloud/run_phase_c_small_v1.sh`
- `scripts/ai/finetune_qlora_small_v1.py`
- `scripts/ai/phase_c_shared.py`
- `scripts/ai/run_phase_c_verification_v1.py`
- `scripts/verify/verify_ai20_bundle_readiness_v1.py`
- `scripts/verify/verify_ai20_server_postrun_v1.py`
- `scripts/verify/verify_ai20_completion_evidence_v1.py`

보조 문서
- `BENCHMARK_KO.md`
- `STATUS_WEEKLY_KO.md`

## 3. 핵심 설정

### QLoRA 고정값
- base model: `Qwen/Qwen3-4B`
- batch size: `3`
- grad accumulation: `6`
- lr: `2.5e-4`
- LoRA r/alpha: `12 / 24`
- max seq length: `1536`
- load_in_4bit: `True`
- bf16: `True`

### Qwen3 고정값
- `enable_thinking=False`
- `chat_template='qwen3_nonthinking'`

## 4. 가장 중요한 fail-closed 규칙

### `STRUCTURE_OK` 와 `READY` 는 다릅니다
- `AI20_BUNDLE_STRUCTURE_OK=1`
  - 코드/구조/dry-run 기준 통과
  - 알고리즘팀 PR 납품 기준
- `AI20_BUNDLE_READY=1`
  - 실제 `train.jsonl`, `validation.jsonl`, output dir, 실행 환경까지 준비 완료
  - 서버 실행 직전 확인 기준

**둘을 혼동하면 안 됩니다.**

### `training-only PASS` 와 `complete PASS` 는 다릅니다
- `--mode training-only`
  - `adapter_model.safetensors` 와 어댑터 구조만 확인
- `--mode complete`
  - Phase C JSON까지 포함한 완료 검증

**training-only PASS는 AI-20 complete가 아닙니다.**

## 5. 로컬 dry-run 실행 순서

```bash
pip install torch transformers peft trl accelerate bitsandbytes sentencepiece datasets pytest

find scripts -name '*.py' | xargs python -m py_compile && echo 'COMPILE_OK=1'       | tee tmp/python_compile_result.txt

python scripts/cloud/apply_small_overlay_v1.py --repo-dir . --dry-run
python scripts/ai/finetune_qlora_small_v1.py --dry-run
python scripts/verify/verify_ai20_bundle_readiness_v1.py --repo-dir . --dry-run

bash -n scripts/cloud/run_training_small_v1.sh  && echo 'TRAIN_SYNTAX_OK=1'
bash -n scripts/cloud/run_phase_c_small_v1.sh   && echo 'PHASE_C_SYNTAX_OK=1'

python -m pytest tests/ -v 2>&1 | tee tmp/unittest_result.txt

grep -n 'enable_thinking\|chat_template\|SAFE_POLICY' scripts/ai/phase_c_shared.py       | tee tmp/qwen3_keyword_review.txt
```

## 6. 학습 실행

```bash
bash scripts/cloud/run_training_small_v1.sh
bash scripts/cloud/run_phase_c_small_v1.sh
```

## 7. 구현 메모

### chat template 처리
가능하면 `tokenizer.apply_chat_template(..., tokenize=True)` 를 우선 사용하십시오.  
문자열 경유가 필요한 경우에는 이후 토큰화 시 `add_special_tokens=False` 를 강제하십시오.

### TRL 버전 차이 대응
본 번들은 `inspect.signature()` 로 `SFTConfig` 와 `SFTTrainer` 시그니처를 조회하여:
- `max_seq_length` 또는 `max_length` 위치를 자동 판별
- `processing_class`, `formatting_func` 지원 여부를 자동 판별

### 금지 사항
- 가짜 `adapter_model.safetensors` 포함 금지
- 가짜 Phase C JSON 포함 금지
- `sample_`, `fake_` 접두사 결과물 혼입 금지
- `__pycache__`, `*.pyc` 포함 금지

## 8. 권장 차기 작업

1. 실제 레포의 AI-19 스크립트와 본 드롭인 버전 diff 적용
2. 실제 GPU 서버에서 소규모 샘플 학습 1회
3. Phase C 20샘플 smoke test
4. MNN export/실기기 latency 회귀 테스트 추가
5. bilingual refusal regression 세트 확대

## 9. 참고
- 공식/최신 벤치마킹 및 차별화 포인트는 `BENCHMARK_KO.md` 참조
- 이번 주 진행 현황은 `STATUS_WEEKLY_KO.md` 참조
