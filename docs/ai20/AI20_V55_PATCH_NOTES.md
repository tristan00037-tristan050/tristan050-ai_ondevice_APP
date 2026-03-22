# AI-20 v55 Patch Notes

## 반영 항목
1. `ready_for_real_gpu_train`를 missing package와 train/eval 파일 존재 기준으로 계산하도록 수정
2. `TrainingArguments` 시그니처를 확인해 `eval_strategy` 또는 `evaluation_strategy`를 자동 선택
3. `torch.cuda.is_bf16_supported()` 기반으로 `bf16` / `fp16` 자동 선택
4. `--resume-from-checkpoint` 경로 인자로 변경
5. `TRAIN_RUN_MANIFEST_PRESENT_OK` / `TRAIN_RUN_MANIFEST_COMPLETE_OK` 분리

## dry-run 결과 요약
- small_default: ready_for_real_gpu_train=0
- micro_default: ready_for_real_gpu_train=0
- 사유: 현재 환경에 `transformers`, `peft`, `bitsandbytes`, `trl`, `datasets`, `accelerate` 미설치
