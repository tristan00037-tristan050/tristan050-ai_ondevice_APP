#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-.}"
cd "$ROOT"

grep -RInE "butler-1\.7b-v5|butler-1\.7b-v4|v4-rt|5e233aab" butler_pc_core/cards/box3 scripts tests/cards/box3 2>/dev/null \
 | grep -v "HISTORICAL_REFERENCE_ONLY" \
 | grep -v "test_v5_v4_default_blocked" \
 | grep -v "BLOCK_V5_DEFAULT_RESIDUE" \
 | grep -v "BLOCK_V4_DEFAULT_REFERENCE" \
 | grep -v "_path_has_v4_reference" \
 | grep -v "_path_has_v5_reference" \
 | grep -v "grep -RInE" \
 | grep -v "safe/ref" \
 | grep -v "v7_asset_manifest.py" \
 | grep -v "v5_asset_manifest.py" \
 | grep -v "test_box3_v5_canonical_apply.py" \
 | grep -v "test_v5_canonical_constants_alg.py" \
 | grep -v "test_v5_degen_and_final_gate_alg.py" \
 | grep -v "test_real_enablement_assets_and_gate.py" \
 | grep -v "test_real_enablement_pipeline.py" \
 | grep -v "test_pr780_regression_lock_alg.py" \
 | grep -v "real_runner_assets.py" \
 | grep -v "lora_fusion/manifest.py" \
 | grep -v "run_box3_v5_real_smoke.py" \
 | grep -v "run_box3_v5_smoke_scenario_audit.py" \
 | grep -v "run_box3_rag_prompt_real_smoke_v1_2.py" \
 | grep -v "run_box3_helper35_lora_fusion_diagnosis.py" \
 | grep -v "run_box3_real_enablement_self_check.py" \
 | grep -v "run_box3_v7_real_smoke.py" \
 | grep -v "test_real_follow_up_enablement_7.py" \
 | grep -v "run_box3_real_activation_v1_3.py" \
 | grep -v "run_box3_real_follow_up_self_check.py" \
 | grep -v "run_box3_real_v1_2_self_check.py" \
 | grep -v "run_box3_helper_sdk_self_check.py" \
 && { echo "BLOCK_OLD_MODEL_DEFAULT_REFERENCE"; exit 1; } || echo "OLD_MODEL_DEFAULT_ZERO=true"

grep -RInE "ALLOW_HELPER35_MULTI_LORA_STACK|lora_path=.*helper[35]" butler_pc_core/cards/box3 scripts 2>/dev/null \
 | grep -v "helper35_runtime_stack_requested" \
 | grep -v "test_no_helper35_restack" \
 | grep -v "verify_box3_v7_canonical_apply_v1_2.sh" \
 | grep -v "v7_asset_manifest.py" \
 | grep -v "BLOCK_HELPER35_DOUBLE_STACK_RISK" \
 | grep -v 'os.environ.pop("BUTLER_BOX3_ALLOW_HELPER35' \
 | grep -v "local_sealed_runner.py" \
 | grep -v "run_box3_v5_real_smoke.py" \
 | grep -v "run_box3_v5_smoke_scenario_audit.py" \
 | grep -v "run_box3_v7_real_smoke.py" \
 | grep -v "run_box3_real_activation_v1_3.py" \
 | grep -v "run_box3_rag_prompt_real_smoke_v1_2.py" \
 && { echo "BLOCK_HELPER35_RUNTIME_STACK"; exit 1; } || echo "HELPER35_RUNTIME_STACK_ZERO=true"

if [ -d evidence/box3_v7_activation ]; then
  grep -RInE "/Users/|/home/|/Volumes/|raw_doc|raw_text|prompt_text|output_text|snippet|sk-proj-|BEGIN PRIVATE KEY" evidence/box3_v7_activation \
   | grep -v "security_zero.txt" \
   && { echo "BLOCK_RAW_OR_PATH_EVIDENCE_LEAK"; exit 1; } || echo "RAW_PATH_SNIPPET_ZERO=true"
else
  echo "RAW_PATH_SNIPPET_ZERO=true"
fi

git diff --name-only 2>/dev/null | grep -E "^schemas/connect_loop/|^docs/ssot/connect_loop/" \
 && { echo "BLOCK_CONNECT_LOOP_MODIFIED"; exit 1; } || echo "CONNECT_LOOP_MODIFIED_ZERO=true"

grep -RInE "production ready|release ready|성능보증|APPROVED_FOR_PRODUCTION" butler_pc_core/cards/box3 scripts tests/cards/box3 evidence/box3_v7_activation 2>/dev/null \
 | grep -v "verify_box3_v7_canonical_apply_v1_2.sh" \
 | grep -v "scripts/ci/check_standard_12.py" \
 | grep -v "scripts/verify_pr_d_sidecar_integration.sh" \
 | grep -v "scripts/verify_box3_endpoint_wiring_v1_2.sh" \
 | grep -v "scripts/verify_box3_actual_operation_v1_2.sh" \
 | grep -v "scripts/verify_admin_policy_ui_followup_v1_2.sh" \
 && { echo "BLOCK_PRODUCTION_CLAIM"; exit 1; } || echo "PRODUCTION_CLAIM_ZERO=true"

grep -RInE "OUTPUT_FORMAT_STRICT" butler_pc_core/cards/box3/grounded_prompt.py >/dev/null \
 && echo "PR785_STRICT_PROMPT_TOKEN_PRESENT=true" || { echo "BLOCK_PRECONDITION_PR785_NOT_MERGED"; exit 1; }

echo "BOX3_V7_CANONICAL_APPLY_VERIFY_PASS=true"
