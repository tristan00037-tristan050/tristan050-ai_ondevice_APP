# Runtime Shadow Mode Proof (Output-Based)

Status: SEALED
RecordedAt(UTC): 2026-02-10T03:48:28Z
PinnedMainHeadSHA: 5d13accee65e7a6b0adc8e078c50d3fb8e9e102f

## Test: Shadow OFF vs ON Response Identity

### Request
```json
{
  "request_id": "proof_test",
  "intent": "ALGO_CORE_THREE_BLOCKS",
  "model_id": "test",
  "device_class": "web",
  "client_version": "test",
  "ts_utc": "2026-01-29T00:00:00Z"
}
```

### Response Blocks (OFF)
```json
{"block_1_policy":{"kind":"policy","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"demoA","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"rules":["meta-only input required","no raw prompt/text/content accepted","fail-closed on unknown keys","pack_salt_bucket:1"]},"block_2_plan":{"kind":"plan","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"demoA","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"steps":["validate meta schema","generate deterministic blocks","emit signed manifest for artifacts"]},"block_3_checks":{"kind":"checks","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"demoA","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"checks":["forbidden keys absent","exactly 3 blocks present","latency recorded"]}}
```

### Response Blocks (ON)
```json
{"block_1_policy":{"kind":"policy","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"demoA","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"rules":["meta-only input required","no raw prompt/text/content accepted","fail-closed on unknown keys","pack_salt_bucket:1"]},"block_2_plan":{"kind":"plan","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"demoA","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"steps":["validate meta schema","generate deterministic blocks","emit signed manifest for artifacts"]},"block_3_checks":{"kind":"checks","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"demoA","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"checks":["forbidden keys absent","exactly 3 blocks present","latency recorded"]}}
```

### Full Response (OFF)
```json
{
  "ok": true,
  "blocks": {
    "block_1_policy": {
      "kind": "policy",
      "meta": {
        "request_id": "proof_test",
        "intent": "ALGO_CORE_THREE_BLOCKS",
        "model_id": "demoA",
        "device_class": "web",
        "client_version": "test",
        "ts_utc": "2026-01-29T00:00:00Z"
      },
      "rules": [
        "meta-only input required",
        "no raw prompt/text/content accepted",
        "fail-closed on unknown keys",
        "pack_salt_bucket:1"
      ]
    },
    "block_2_plan": {
      "kind": "plan",
      "meta": {
        "request_id": "proof_test",
        "intent": "ALGO_CORE_THREE_BLOCKS",
        "model_id": "demoA",
        "device_class": "web",
        "client_version": "test",
        "ts_utc": "2026-01-29T00:00:00Z"
      },
      "steps": [
        "validate meta schema",
        "generate deterministic blocks",
        "emit signed manifest for artifacts"
      ]
    },
    "block_3_checks": {
      "kind": "checks",
      "meta": {
        "request_id": "proof_test",
        "intent": "ALGO_CORE_THREE_BLOCKS",
        "model_id": "demoA",
        "device_class": "web",
        "client_version": "test",
        "ts_utc": "2026-01-29T00:00:00Z"
      },
      "checks": [
        "forbidden keys absent",
        "exactly 3 blocks present",
        "latency recorded"
      ]
    }
  },
  "pack_id": "demoA",
  "version": "0.0.1",
  "manifest": {
    "sha256": "85e936c69d0c15b615ad2ae6a0f09e86a13fa06bf02054b3013d1c25f22215d8"
  },
  "signature": {
    "b64": "X+0thOboPyPqifkqRzl7LPwnVkbkHxiQp0OFXIxy+otVboLW/y9+L8W/Y8RBemrb22QELrYv2cZIK1L6DhvrAQ==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQU9PZGFESy95ZEs3MjRwU0VSWklKQTRBYmJkMzZ3c3pBSnFRY0g2TlYrRGs9Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
    "mode": "dev"
  },
  "result_fingerprint_sha256": "5278c8ced22bdd4e59aa23f9d8f4cebf2ad4aa339bfde2941716b71843b16300",
  "compute_path": "ondevice"
}
```

### Full Response (ON)
```json
{
  "ok": true,
  "blocks": {
    "block_1_policy": {
      "kind": "policy",
      "meta": {
        "request_id": "proof_test",
        "intent": "ALGO_CORE_THREE_BLOCKS",
        "model_id": "demoA",
        "device_class": "web",
        "client_version": "test",
        "ts_utc": "2026-01-29T00:00:00Z"
      },
      "rules": [
        "meta-only input required",
        "no raw prompt/text/content accepted",
        "fail-closed on unknown keys",
        "pack_salt_bucket:1"
      ]
    },
    "block_2_plan": {
      "kind": "plan",
      "meta": {
        "request_id": "proof_test",
        "intent": "ALGO_CORE_THREE_BLOCKS",
        "model_id": "demoA",
        "device_class": "web",
        "client_version": "test",
        "ts_utc": "2026-01-29T00:00:00Z"
      },
      "steps": [
        "validate meta schema",
        "generate deterministic blocks",
        "emit signed manifest for artifacts"
      ]
    },
    "block_3_checks": {
      "kind": "checks",
      "meta": {
        "request_id": "proof_test",
        "intent": "ALGO_CORE_THREE_BLOCKS",
        "model_id": "demoA",
        "device_class": "web",
        "client_version": "test",
        "ts_utc": "2026-01-29T00:00:00Z"
      },
      "checks": [
        "forbidden keys absent",
        "exactly 3 blocks present",
        "latency recorded"
      ]
    }
  },
  "pack_id": "demoA",
  "version": "0.0.1",
  "manifest": {
    "sha256": "d104df45fa9fca4d7b46f5c66ca5d3d62f576b80531328fe5e53e2106667b3b1"
  },
  "signature": {
    "b64": "+m9mX8LIsM8cwyb4D3UytU8cqlYWDhbur5XgYiyK4CPafK2BC9xd1RnHFDYuBbhUkeqvS21yJmLSFl+/C7oeCw==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQWp4T0MzNVQxRFhtaW4yZHpHWFRpZWl3emswVGxGaXZlYkZsZ2M2cVErdkk9Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
    "mode": "dev"
  },
  "result_fingerprint_sha256": "5278c8ced22bdd4e59aa23f9d8f4cebf2ad4aa339bfde2941716b71843b16300",
  "compute_path": "ondevice"
}
```

### Critical Headers (OFF)
```
X-OS-Algo-Latency-Ms: 1.227
X-OS-Algo-Manifest-SHA256: 85e936c69d0c15b615ad2ae6a0f09e86a13fa06bf02054b3013d1c25f22215d8
```

### Critical Headers (ON)
```
X-OS-Algo-Latency-Ms: 1.185
X-OS-Algo-Manifest-SHA256: d104df45fa9fca4d7b46f5c66ca5d3d62f576b80531328fe5e53e2106667b3b1
```

## Output-Based Checks

- Response blocks identical: PASS
- Response ok field identical: PASS
- X-OS-Algo-Latency-Ms header present (both): PASS
- X-OS-Algo-Manifest-SHA256 header present (both): PASS
- Shadow does not modify user response blocks: PASS

## DoD Keys

- RUNTIME_SHADOW_ENDPOINT_OK=1
- RUNTIME_SHADOW_HEADERS_OK=1
- BFF_SHADOW_FIREFORGET_OK=1
- RUNTIME_SHADOW_PROOF_OK=1
