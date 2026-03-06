#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_YAML_PARSE_OK=0
trap 'echo "WORKFLOW_YAML_PARSE_OK=${WORKFLOW_YAML_PARSE_OK}"' EXIT

ENFORCE="${WORKFLOW_YAML_PARSE_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "WORKFLOW_YAML_PARSE_SKIPPED=1"
  exit 0
fi

# Fail-closed: require ruby present when ENFORCE=1
command -v ruby >/dev/null 2>&1 || { echo "ERROR_CODE=RUBY_MISSING"; exit 1; }

# Parse all workflow YAML files
found=0
while IFS= read -r f; do
  found=1
  ruby -ryaml -e 'YAML.load_file(ARGV[0])' "$f" >/dev/null
done < <(find .github/workflows -maxdepth 1 -type f \( -name "*.yml" -o -name "*.yaml" \) 2>/dev/null | sort)

[ "$found" -eq 1 ] || { echo "ERROR_CODE=NO_WORKFLOW_FILES"; exit 1; }

WORKFLOW_YAML_PARSE_OK=1
exit 0
