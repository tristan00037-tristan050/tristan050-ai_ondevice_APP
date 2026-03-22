# AI-20 v58 Patch Notes

## What changed

### 1. Real-train fail-closed is now enforced in code
- Added `enforce_real_train_fail_closed(git_sha, strategy_meta)` to `scripts/ai/finetune_qlora_small_v1.py`.
- Real training now aborts before model load when:
  - `git_sha == "UNKNOWN"`
  - `training_arguments_strategy_key_resolved is None`

### 2. Dry-run vs real-train strategy-key status is explicitly separated
- Dry-run result keeps:
  - `effective_sft_kwargs_scope=config_assuming_runtime_ready`
  - `training_arguments_strategy_key_assumed`
- Real training requires:
  - `TRAINING_ARGUMENTS_STRATEGY_KEY_RESOLVED_FOR_REAL_RUN_OK=1`

### 3. Code-level verifier added
- New file: `scripts/verify/verify_ai20_real_train_failclosed_v1.py`
- Verifies three cases:
  1. unresolved git SHA must fail
  2. unresolved TrainingArguments strategy key must fail
  3. resolved git SHA + resolved strategy key must pass

## Included evidence
- `tmp/ai20_small_default_dryrun_result.json`
- `tmp/ai20_micro_default_dryrun_result.json`
- `tmp/ai20_train_input_sanity_result.json`
- `tmp/ai20_real_train_failclosed_check.json`
- `tmp/ai20_v58_overview.json`

## Interpretation
- This bundle is intended to be the final pre-real-train checkpoint.
- Dry-run may still show `training_arguments_strategy_key_resolved=null` when Transformers is not installed.
- Real training will fail closed until that key is resolved in the actual runtime.
