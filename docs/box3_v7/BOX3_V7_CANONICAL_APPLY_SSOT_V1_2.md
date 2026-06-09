# Box 3 v7 canonical apply SSOT v1.2

STATUS=PASS_CONTRACT_PACKAGE_V7_CANONICAL_LOCAL_SMOKE_PENDING

## Scope

This package switches Box 3 canonical base configuration from earlier operational defaults to the v7 canonical GGUF contract:

- `butler-1.7b-v7-q4_k_m.gguf`
- q4 SHA-256 `a8440e984a2d0899049df7166aeff32d9bfb2881e614aa55b029b4a7eead5621`
- f16 source-sealed SHA-256 `6ff70adf08130c11a4ece523f33b2b8d4d2118187805a458661fe7c62d5be7f1`
- runtime helper3/helper5 LoRA restacking is blocked.
- helper4/helper7/helper8 remain SDK modules.
- production claim remains false.

## PR #785 precondition

The package absorbs the `OUTPUT_FORMAT_STRICT` and abstain requirements in `grounded_prompt.py`, but it does not claim that PR #785 is merged in main. Deployment must verify that PR #785 is either merged or these modules are applied in the same integration PR.

## Hard gates

- v7 q4 file SHA must match exactly.
- v4/v5 operational default residue is blocked.
- helper3/helper5 runtime restack is blocked.
- unsupported claim count must be zero.
- degeneration must be false.
- abstain marker must be exactly `[문서에 근거 없음]`.
- abstain ratio must be <= 0.60.
- citation accuracy must be >= 0.95.
- section completeness must be >= 0.67.
- production_claim_allowed=false remains fixed.

## Evidence policy

Only digest/count/metric evidence may persist. No reference text, prompt text, output text, snippet, absolute local path, secret, or raw document field is allowed.
