#!/usr/bin/env bash
set -euo pipefail

# 1) workflow-lint.yml에 위험 권한/attestation 스텝이 남아 있으면 즉시 실패(fail-closed)
FILE=".github/workflows/workflow-lint.yml"

grep -n "id-token:[[:space:]]*write" "$FILE" && { echo "BLOCK: workflow-lint has id-token: write"; exit 1; } || true
grep -n "attestations:[[:space:]]*write" "$FILE" && { echo "BLOCK: workflow-lint has attestations: write"; exit 1; } || true
grep -n "artifact-metadata:[[:space:]]*write" "$FILE" && { echo "BLOCK: workflow-lint has artifact-metadata: write"; exit 1; } || true
grep -n "attest-build-provenance" "$FILE" && { echo "BLOCK: workflow-lint runs attest-build-provenance"; exit 1; } || true

# 2) 필수 도구가 없거나 실행할 수 없으면 검증 성공으로 간주하지 않는다.
command -v python3 >/dev/null 2>&1 || {
  echo "BLOCK: python3 is required for workflow parsing"
  exit 1
}
command -v actionlint >/dev/null 2>&1 || {
  echo "BLOCK: checksum-verified actionlint is required"
  exit 1
}

# 3) .yml/.yaml 전체를 파싱하고 job-level runner context 사용을 차단한다.
python3 - <<'PY'
import pathlib
import sys

try:
    import yaml
except Exception as exc:
    print(f"BLOCK: PyYAML is required: {type(exc).__name__}")
    sys.exit(1)

paths = sorted(
    {
        *pathlib.Path(".github/workflows").glob("*.yml"),
        *pathlib.Path(".github/workflows").glob("*.yaml"),
    }
)
if not paths:
    print("BLOCK: no workflow files found")
    sys.exit(1)

bad = []
for path in paths:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise TypeError("workflow root must be a mapping")
        jobs = document.get("jobs", {})
        if not isinstance(jobs, dict):
            raise TypeError("jobs must be a mapping")
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            env = job.get("env", {})
            if isinstance(env, dict):
                for key, value in env.items():
                    if isinstance(value, str) and "${{ runner." in value:
                        bad.append(
                            (str(path), f"job {job_id!r} env {key!r} uses runner context")
                        )
    except Exception as exc:
        bad.append((str(path), f"{type(exc).__name__}: {exc}"))

if bad:
    print("Workflow parse/contract errors:")
    for filename, error in bad:
        print(f"- {filename}: {error}")
    sys.exit(1)
print(f"Workflow YAML parse OK: files={len(paths)}")
PY

# 4) actionlint 자체가 실패하거나 사용할 수 없으면 그대로 실패한다.
find .github/workflows -maxdepth 1 -type f \
  \( -name '*.yml' -o -name '*.yaml' \) -print0 \
  | sort -z \
  | xargs -0 actionlint

echo "workflow-lint OK"
