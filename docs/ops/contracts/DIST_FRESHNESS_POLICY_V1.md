# DIST_FRESHNESS_POLICY_V1

DIST_FRESHNESS_POLICY_V1_TOKEN=1

규칙(고정):
- dist 빌드는 workflow preflight에서만 수행한다.
- verify는 빌드를 수행하지 않고, stamp 존재/일치만 판정한다.
- stamp 파일(meta-only): dist/.build_stamp.json
  필수 필드: git_sha, built_at_utc, workflow_name
- stamp.git_sha가 현재 HEAD와 다르면 BLOCK.

