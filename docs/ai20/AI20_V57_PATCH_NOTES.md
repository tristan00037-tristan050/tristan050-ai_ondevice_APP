AI-20 v57 patch notes

What changed
- Separated expected training config from runtime-proven config with:
  - `effective_sft_kwargs_scope`
  - `training_arguments_strategy_key_resolved`
  - `training_arguments_strategy_key_assumed`
  - `training_arguments_strategy_key_resolution_source`
- Tightened manifest completeness criteria to require:
  - resolved `git_sha`
  - tokenizer digest
  - train file digest
  - requirements lock digest
  - effective kwargs
  - start/end UTC timestamps
  - checkpoint artifact digest
- Added fail-closed real-train condition:
  - `git rev-parse HEAD` must resolve, otherwise training aborts.
- Added large-scale synthetic_v40 dataset builder and regenerated dataset.
- Expanded train input sanity verification to include:
  - global duplicate prompt rate
  - function coverage
  - language coverage
  - over-max-sequence ratio
  - tool_call strict schema validation
  - scale readiness

Current dry-run state
- config_ready_for_training = 1
- runtime_ready_for_training = 0
- ready_for_real_gpu_train = 0
- TRAIN_RUN_MANIFEST_PRESENT_OK = 1
- TRAIN_RUN_MANIFEST_COMPLETE_OK = 0
- AI20_TRAIN_INPUT_SANITY_OK = 1
- AI20_TRAIN_INPUT_SCALE_READY_OK = 1
- DATASET_SPLIT_NO_LEAKAGE_OK = 1
- TOOL_CALL_SCHEMA_STRICT_OK = 1
