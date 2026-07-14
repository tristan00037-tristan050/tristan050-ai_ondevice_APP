#!/usr/bin/env bash
set -euo pipefail
umask 077

test -f evidence/ci/actual_integration.json
python3 - <<'PY'
import json
from pathlib import Path
value=json.loads(Path('evidence/ci/actual_integration.json').read_text(encoding='utf-8'))
assert value['route_semantics_changed'] is False
assert value['runtime_activation_allowed'] == 0
assert value['production_gate_event_count'] >= 5
print('{"status":"PASS","route_semantics_changed":false,"runtime_activation_allowed":0}')
PY
