# ONPREM-02b Helm Secrets Guard — SEALED Record

This record permanently pins the ONPREM-02b change set (P2 guard) to prevent drift.

## Evidence (GitHub)
- PR: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/238
- merged: true
- merged_at (UTC): 2026-01-27T03:20:32Z
- merge_commit_sha: 9a68eadc1ebd5a7744d438c9acbea3bc9f0de140

## Scope (what ONPREM-02b enforces)
- `secrets.enabled=true`: chart creates the release Secret.
- `secrets.enabled=false`: operator must set `secrets.existingSecretName` and pre-create that Secret.
- Fail-closed: `secrets.enabled=false` and empty `existingSecretName` must fail at Helm render/install.

## DoD (output-based)
- Repo-guards key:
  - `ONPREM_HELM_SECRETS_GUARD_OK=1`

## Verification (local, output-only)
```bash
bash scripts/verify/verify_repo_contracts.sh ; echo EXIT=$?
# Expect:
#   ONPREM_HELM_SECRETS_GUARD_OK=1
#   EXIT=0
```

## Changed files (from PR #238)
- scripts/verify/verify_onprem_helm_secrets_guard.sh
- scripts/verify/verify_repo_contracts.sh
- webcore_appcore_starter_4_17/docs/ONPREM_HELM_DEPLOYMENT.md
- webcore_appcore_starter_4_17/helm/onprem-gateway/templates/deployment.yaml
- webcore_appcore_starter_4_17/helm/onprem-gateway/templates/secret.yaml
- webcore_appcore_starter_4_17/helm/onprem-gateway/values.schema.json
- webcore_appcore_starter_4_17/helm/onprem-gateway/values.yaml

SEALED rule
- No placeholders / TODO.
- Evidence must be output-based.
