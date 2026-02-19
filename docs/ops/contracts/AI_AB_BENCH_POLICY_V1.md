# AI_AB_BENCH_POLICY_V1

AI_AB_BENCH_POLICY_V1_TOKEN=1

# Runs policy (2-tier)
RUNS_PR=10
RUNS_NIGHTLY=200
WARMUP=5

# Budgets / thresholds (meta-only)
P95_BUDGET_MS=50
OUTLIER_RATE_MAX=0.02

# Notes
- PR runs must be short; nightly runs must be long. RUNS_NIGHTLY must be strictly greater than RUNS_PR.
- Outputs must be meta-only (raw=0). No long text, no array dumps.
