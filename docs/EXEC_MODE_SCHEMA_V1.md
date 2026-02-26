# Exec Mode V1 Schema

## Input: prompts (JSONL)

One JSON object per line.

| Field   | Type   | Required | Description |
|---------|--------|----------|-------------|
| `id`    | string | yes      | Unique request id (e.g. smoke-1). |
| `prompt`| string | yes      | User prompt text. |

Example:

```json
{"id":"smoke-1","prompt":"Say hello in one word."}
```

## Output: result (JSONL)

One JSON object per line; one line per input line, same order.

| Field    | Type   | Required | Description |
|----------|--------|----------|-------------|
| `id`     | string | yes      | Same as input `id`. |
| `prompt` | string | yes      | Echo of input prompt. |
| `result` | string | yes      | Engine output (e.g. `[mock] OK`). |
| `engine` | string | yes      | Engine id (e.g. `mock`). |
| `ts_utc` | string | yes      | ISO 8601 UTC timestamp. |

Example:

```json
{"id":"smoke-1","prompt":"Say hello in one word.","result":"[mock] OK","engine":"mock","ts_utc":"2026-02-19T12:00:00Z"}
```

## Verification (fail-closed)

- `result.jsonl` must exist under `--outdir`.
- Result line count must be ≥ input line count.
- Each result line must be valid JSON and contain `id` and `result`.
- Any violation → verifier exits non-zero and does **not** emit `EXEC_MODE_V1_OK=1`.
