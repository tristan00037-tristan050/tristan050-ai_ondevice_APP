#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install -U pip
if [ "${BUTLER_ALLOW_BREAK_SYSTEM_PACKAGES:-0}" = "1" ]; then
  python3 -m pip install -r requirements-box2-helper3.txt --break-system-packages
else
  python3 -m pip install -r requirements-box2-helper3.txt
fi
