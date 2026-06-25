#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "$*=true"; }

test -f scripts/build_runtime.sh || fail "scripts/build_runtime.sh missing — run from repo root after patch apply"
test -f butler-desktop/src-tauri/src/lib.rs || fail "lib.rs missing — run from repo root after patch apply"
test -f butler-desktop/src-tauri/tauri.conf.json || fail "tauri.conf.json missing — run from repo root after patch apply"

bash -n scripts/build_runtime.sh
pass BUILD_RUNTIME_BASH_N_PASS

grep -q 'BOX3_V9_2_R2B_BUNDLE_STAGE_DONE' scripts/build_runtime.sh || fail "build_runtime missing absorbed Box3 v2.4 stage"
grep -q 'aae4ea7a4ebe0586db3317d5209b5565abcd326ea73decb7ffa99f433c218847' scripts/build_runtime.sh || fail "build_runtime missing v9.2-r2b sha"
grep -q 'HELPER35_RUNTIME_STACK_BUNDLE_FORBIDDEN' scripts/build_runtime.sh || fail "build_runtime missing helper35 safetensors guard"
grep -q 'BUTLER_HELPER2_EMBEDDING_SRC' scripts/build_runtime.sh || fail "build_runtime missing helper2 embedding asset hook"
grep -q 'BUTLER_BOX3_FIXED_EVAL_REPORT_SRC' scripts/build_runtime.sh || fail "build_runtime missing fixed eval report source hook"
pass BUILD_RUNTIME_BOX3_ABSORBED

python3 - <<'PY'
import json
from pathlib import Path
conf = json.loads(Path('butler-desktop/src-tauri/tauri.conf.json').read_text(encoding='utf-8'))
resources = conf['bundle']['resources']
if resources.get('models') != 'models':
    raise SystemExit('models recursive resource mapping missing')
if any(str(k).endswith('models/box3') or str(v).endswith('models/box3') for k, v in resources.items()):
    raise SystemExit('duplicate models/box3 resource mapping forbidden')
print('TAURI_MODELS_RECURSIVE_RESOURCE_OK=true')
PY

grep -q 'push_box3_resource_env' butler-desktop/src-tauri/src/lib.rs || fail "lib.rs missing Box3 resource env function"
grep -q 'path.exists() && !values.iter().any' butler-desktop/src-tauri/src/lib.rs || fail "lib.rs missing exists/no-override guard"
grep -q 'BOX3_EXTRA_ENV_KEYS' butler-desktop/src-tauri/src/lib.rs || fail "lib.rs missing explicit env/config keys"
grep -q 'BUTLER_HELPER4_GROUNDING_SDK_PATH' butler-desktop/src-tauri/src/lib.rs || fail "lib.rs missing helper4 sdk env"
grep -q 'BUTLER_BOX3_FIXED_EVAL_REPORT_PATH' butler-desktop/src-tauri/src/lib.rs || fail "lib.rs missing fixed eval env"
pass LIBRS_RESOURCE_ENV_GUARDED

grep -R "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL.*READY" -n . --exclude-dir=.git --exclude=verify_box3_bundle_activation_v2_4.sh && fail "runtime PASS overclaim" || true
grep -RInE '^[[:space:]]*(Co-Authored-By:|Generated (by Claude|with Claude Code))' . --exclude-dir=.git --exclude='verify_*' && fail "AI footer detected" || true
pass CLAIM_AND_FOOTER_ZERO

find . -type d -name __pycache__ -print -quit | grep -q . && fail "__pycache__ present" || true
git ls-files 'butler-desktop/src-tauri/models/*' 'butler-desktop/src-tauri/python-runtime/*' 2>/dev/null | grep -E '\.(gguf|safetensors|bin)$' && fail "tracked bundled binary/model artifact present" || true
pass TRACKED_MODEL_BINARY_ZERO

if [[ -d butler-desktop/src-tauri/models ]]; then
  find butler-desktop/src-tauri/models -type f \( -iname '*helper3*.safetensors' -o -iname '*helper5*.safetensors' -o -iname '*format*adapter*.safetensors' -o -iname '*tool*call*.safetensors' \) -print -quit | grep -q . && fail "bundled helper3/5 safetensors artifact detected" || true
fi
pass HELPER35_RESTACK_ZERO

PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-${TMPDIR:-/tmp}/butler_box3_verify_pyc}" \
  python3 -m py_compile butler_pc_core/cards/box3/bundle_activation.py scripts/box3_verify_runtime_assets.py
pass PY_COMPILE_PASS

echo "BOX3_BUNDLE_ACTIVATION_V2_4_VERIFY_PASS=true"
