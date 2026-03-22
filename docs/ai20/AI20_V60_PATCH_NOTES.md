AI-20 v60 patch notes

Changes
- Bundle version unified to v60.
- Removed temporary verifier Git metadata under tmp/ai20_cli_failclosed/repo_case/.git.
- Removed Python bytecode cache artifacts (__pycache__, *.pyc).
- Added artifact cleanliness flags to overview JSON.

Result
- ARTIFACTS_NO_PYCACHE_OK=1
- ARTIFACTS_NO_TMP_GIT_OK=1
