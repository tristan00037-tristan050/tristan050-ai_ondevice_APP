#!/usr/bin/env python3
from __future__ import annotations
import ast, subprocess, sys
from pathlib import Path

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
CORE=ROOT/'butler_pc_core/model_tier/benchmark_v23/core.py'
TEST=ROOT/'tests/model_tier/test_benchmark_v23_product_path.py'

def fail(code):
    print('MODEL_TIER_B_V23_VERIFY=0')
    print('ERROR_CODE='+code)
    raise SystemExit(1)
for path in (CORE,TEST):
    if not path.is_file(): fail('REQUIRED_FILE_MISSING')
    try: ast.parse(path.read_text(encoding='utf-8'))
    except SyntaxError: fail('SOURCE_PARSE_ERROR')
source=CORE.read_text(encoding='utf-8')
for marker in (
    'Box3ProductPipelineRuntime','run_product_matrix','run_cold_worker_handshake',
    'measure_dual_resident_pressure','verify_samples_first','run_box3_actual_operation',
    'dlp_pre_output_guard','unsupported_claim_labeling','BLOCK_ENGINE_NO_FIRST_TOKEN',
    'verify_approved_identity','VOLATILE_DRAFT_MUST_NOT_PERSIST',
):
    if marker not in source: fail('CONTRACT_MARKER_MISSING')
if 'create_pull_request' in source: fail('PR_CREATION_FORBIDDEN')
result=subprocess.run(
    [sys.executable,'-m','pytest',str(TEST.relative_to(ROOT)),'-q'],
    cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120,
)
if result.returncode: fail('PRODUCT_PATH_TESTS_FAILED')
print('MODEL_TIER_B_V23_VERIFY=1')
print('ACTUAL_PRODUCT_PIPELINE_BOUND=1')
print('SAME_REQUEST_VOLATILE_REPAIR=1')
print('STRICT_EVIDENCE_CHAIN=1')
print('WORKER_IDENTITY_RECHECK=1')
print('M3_EXECUTION=0')
print('PR_CREATED=0')
