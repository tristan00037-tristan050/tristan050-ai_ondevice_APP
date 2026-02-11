#!/usr/bin/env bash
set -euo pipefail

# 1) workflow-lint.yml에 위험 권한/attestation 스텝이 남아 있으면 즉시 실패(fail-closed)
FILE=".github/workflows/workflow-lint.yml"

grep -n "id-token:[[:space:]]*write" "$FILE" && { echo "BLOCK: workflow-lint has id-token: write"; exit 1; } || true
grep -n "attestations:[[:space:]]*write" "$FILE" && { echo "BLOCK: workflow-lint has attestations: write"; exit 1; } || true
grep -n "artifact-metadata:[[:space:]]*write" "$FILE" && { echo "BLOCK: workflow-lint has artifact-metadata: write"; exit 1; } || true
grep -n "attest-build-provenance" "$FILE" && { echo "BLOCK: workflow-lint runs attest-build-provenance"; exit 1; } || true

# 2) YAML 파싱(가능한 환경이면)
python - <<'PY'
import pathlib, sys
try:
    import yaml
except Exception:
    print("PyYAML not installed; skip parse")
    sys.exit(0)

bad=[]
for p in pathlib.Path(".github/workflows").glob("*.yml"):
    try:
        yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        bad.append((str(p), str(e)))
if bad:
    print("YAML parse errors:")
    for f,e in bad:
        print(f"- {f}: {e}")
    sys.exit(1)
print("Workflow YAML parse OK")
PY

echo "workflow-lint OK"
