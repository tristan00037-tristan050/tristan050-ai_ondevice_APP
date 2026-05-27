#!/usr/bin/env bash
set -euo pipefail
PYTHONPATH=. python3 -m pytest tests/cards/box2 -v
grep -RInE "requests\.|httpx\.|aiohttp\.|urllib|fetch\(|axios" butler_pc_core/cards/box2 | grep -v "localhost" | grep -v "127.0.0.1" && { echo "BLOCK_EXTERNAL_SEND_RISK"; exit 1; } || echo "EXTERNAL_SEND_RISK_ZERO=true"
grep -RInE "foreign_doc|our_format|raw_doc|raw_text|prompt|input_text|file_path|filename" evidence/box2_helper3 && { echo "BLOCK_RAW_PERSISTENCE_RISK"; exit 1; } || echo "RAW_PERSISTENCE_RISK_ZERO=true"
