# MODEL_PACK_CATALOG_V1 Guide

Machine SSOT: `docs/ops/contracts/MODEL_PACK_CATALOG_V1.json`
Verifier: `scripts/verify/verify_model_pack_catalog_v1.sh`

## Schema

| Field | Type | Description |
|-------|------|-------------|
| schema_version | int | Must be 1 |
| packs | array | List of registered model packs |

### Pack fields (all required)

| Field | Type | Description |
|-------|------|-------------|
| pack_id | string | Unique pack identifier |
| tier | string | Capacity tier: `micro` or `small` |
| quant | string | Quantization: `int4` |
| runtime_id | string | Runtime that loads this pack |
| weights_digest_sha256 | string | SHA-256 of weights file (`REQUIRED` until real weights land) |
| tokenizer_digest_sha256 | string | SHA-256 of tokenizer file |
| config_digest_sha256 | string | SHA-256 of config file |
| min_ram_mb | int | Minimum RAM in MB required to load the pack |
| latency_budget_ms_p95 | int | P95 latency budget in milliseconds |

## Registered packs

| pack_id | tier | min_ram_mb | latency_budget_ms_p95 |
|---------|------|------------|----------------------|
| micro_default | micro | 1500 | 1200 |
| small_default | small | 3000 | 2000 |

## Rules

1. Every pack in `packs/` MUST have an entry in this catalog.
2. `weights_digest_sha256`, `tokenizer_digest_sha256`, `config_digest_sha256` are `REQUIRED` until real weights land.
3. When real weights land, replace `REQUIRED` with the actual SHA-256 digest.
4. `latency_budget_ms_p95` is a hard gate enforced by `verify_perf_real_pipeline_p95.sh`.
