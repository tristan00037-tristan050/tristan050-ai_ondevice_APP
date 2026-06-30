# Box5 rulebase learning autoflow local validation evidence

Date: 2026-06-30
Branch: feat/box5-rulebase-learning-autoflow-codex

## Raw measured results

- `python3 -m py_compile butler_pc_core/accounting/rulebase_learning/contracts.py butler_pc_core/accounting/rulebase_learning/candidate_gate.py butler_pc_core/accounting/rulebase_learning/queue.py butler_pc_core/accounting/rulebase_learning/diff_builder.py butler_pc_core/accounting/rulebase_learning/runner.py` -> PASS
- `python3 -m pytest tests/accounting/test_rulebase_learning_autoflow.py -q` -> 21 passed
- `python3 -m pytest tests/accounting -q` -> 162 passed
- `python3 -m pytest tests/connect_loop -q` -> 589 passed, 2 skipped
- Current repo direct evaluation using `butler-ct-shared/code_archive/box5_transfer_guard/eval/box5_guard_eval.json` -> recall 1.000 (34/34), specificity 1.000 (15/15), trap_caught 0/8

## Scope notes

- No `usage_log_v1_1.schema.json` or `learning_event_v1.schema.json` change.
- No Box5 live classifier/guard logic change for the new learning autoflow. One existing test expectation was aligned with the already-present `수도광열비` domain override.
- Official Group A fixed eval content is referenced by SHA instead of copied, because the dataset contains account-number-like examples and this branch SSOT keeps raw/plain account material out of new artifacts.
