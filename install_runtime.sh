#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install -U pip

if [ "${BUTLER_ALLOW_BREAK_SYSTEM_PACKAGES:-0}" = "1" ]; then
  python3 -m pip install mlx-lm peft transformers --break-system-packages
else
  python3 -m pip install mlx-lm peft transformers
fi
