# EXEC_MODE_SCHEMA_V1

## Input (JSONL)
Each line is a JSON object:
- `id` (string, required): non-empty
- `prompt` (string, optional)
- `params` (object, optional)

## Output (JSONL)
Each line is a JSON object:
- `id` (string, required): must match input id line-by-line
- `result` (string, required): `OK` or `BLOCK` (v1)
- `exit_code` (number, required): `0` for OK, `1` for BLOCK
- `latency_ms` (number, required)
- `tokens_out` (number|null, required): v1 allows null. For ondevice_candidate_v0 it is always null.
- `engine_meta` (object, required)
  - `engine` (string, required): `mock` or `ondevice_candidate_v0`
  - `tokens_out_supported` (boolean, required): must be `false` in v1
  - `result_fingerprint_sha256` (string|null, required): optional evidence for real-compute candidate; null if not available
