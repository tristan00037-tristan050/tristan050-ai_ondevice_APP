#!/usr/bin/env bash
set -euo pipefail
umask 077

python3 -m butler_bench.owner_runner "$@"
