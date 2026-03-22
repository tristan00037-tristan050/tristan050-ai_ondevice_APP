# AI-20 v56 Patch Notes

## Fixed
- Added `config_ready_for_training` and `runtime_ready_for_training` to dry-run outputs.
- Strengthened `TRAIN_RUN_MANIFEST_COMPLETE_OK` criteria to require:
  git_sha, tokenizer digest, train file sha256, requirements lock sha256,
  effective kwargs, start_utc, end_utc, checkpoint artifact digest.
- Split dependency declarations into `requirements.train.txt` (ranges) and `requirements.lock` (pinned top-level stack).
- Added `scripts/verify/verify_ai20_train_input_sanity_v1.py` for dataset integrity checks.
- Removed `__pycache__` from bundle.

## Notes
- In dry-run, `TRAIN_RUN_MANIFEST_COMPLETE_OK=0` is expected.
- In non-git zip environments, `git_sha` may be `UNKNOWN`, so manifest completeness remains 0 until real training is executed in-repo.
