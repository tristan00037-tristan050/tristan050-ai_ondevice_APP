AI-20 v59 patch notes

What changed
- Unified current bundle version references to v59 in the zip/root/README/current overview.
- Moved real-train fail-closed enforcement ahead of heavy runtime imports so the CLI aborts before model load.
- Added CLI-level fail-closed verifier: scripts/verify/verify_ai20_real_train_cli_failclosed_v1.sh
- Strengthened README with a top-level warning box for real-train prerequisites.

Why
- The previous bundle already had function-level fail-closed enforcement, but the last operational gap was proving the same behavior through the actual CLI entry path.
- Version label drift between zip/root/README/current notes could create ambiguity in operations and provenance tracking.

Current interpretation
- dry-run may keep training_arguments_strategy_key_assumed when runtime inspection is unavailable.
- real train must have git SHA resolved and TrainingArguments strategy key resolved, otherwise training aborts before heavy imports and model load.
