#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pytest -q tests/cards/box2
python3 scripts/run_box2_helper3_v2_preflight.py
