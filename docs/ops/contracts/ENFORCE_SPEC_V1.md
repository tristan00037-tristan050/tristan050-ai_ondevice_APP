ENFORCE_SPEC_V1_TOKEN=1

# Rules
# - <FEATURE>_ENFORCE=1 => ENFORCE (fail-closed)
# - default => SKIP
# - Even on SKIP, keys must not be missing:
#   <FEATURE>_OK=0
#   <FEATURE>_SKIPPED=1
#
# Verifiers must not parse *_ENFORCE directly.
# They must use scripts/verify/lib/enforce_spec_v1.sh only.
