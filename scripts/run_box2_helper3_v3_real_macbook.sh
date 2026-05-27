#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH=.
export BUTLER_BOX2_RUN_REAL_V3=1
python3 -m pytest tests/cards/box2/test_runtime_real_v3.py -v
python3 -m pytest tests/cards/box2/test_real_load_smoke_v3.py -v
python3 -m pytest tests/cards/box2/test_real_metric_v3.py -v
bash scripts/run_box2_helper3_v3_contract_tests.sh
