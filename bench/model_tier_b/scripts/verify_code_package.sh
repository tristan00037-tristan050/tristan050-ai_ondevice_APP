#!/usr/bin/env bash
set -euo pipefail
umask 077

python3 -m compileall -q butler_bench offline_verifier scripts tests
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -c 'from pathlib import Path; from butler_bench.independence import assert_offline_verifier_independent; assert_offline_verifier_independent(Path("offline_verifier/verify.py"))'
