# Box5 rulebase learning autoflow SSOT

This directory pins the Codex implementation artifacts for `verified_rule_base_candidate.v1` and the Box5 rulebase learning autoflow.

Included:
- implementation copies of `butler_pc_core/accounting/rulebase_learning/*.py`
- schema copy for `schemas/box5/verified_rule_base_candidate_v1.schema.json`
- tests that lock the new contract, queue, diff builder, runner, and existing path separation
- safe sample PR-candidate diff and manifest
- SHA reference to the official Group A fixed guard eval set

Not included:
- raw transaction memo, filename, md content, account plaintext, model artifact, auto-applied patch, commit/push automation, PR creation automation
