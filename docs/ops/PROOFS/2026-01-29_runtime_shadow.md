# Runtime Shadow Mode Proof (Output-Based)

Status: SEALED
RecordedAt(UTC): 2026-01-31T05:42:59Z
PinnedMainHeadSHA: d57524edc8a3c748965431c0e54eeb3b61ecc81f

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
{"block_1_policy":{"kind":"policy","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"test","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"rules":["meta-only input required","no raw prompt/text/content accepted","fail-closed on unknown keys"]},"block_2_plan":{"kind":"plan","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"test","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"steps":["validate meta schema","generate deterministic blocks","emit signed manifest for artifacts"]},"block_3_checks":{"kind":"checks","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"test","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"checks":["forbidden keys absent","exactly 3 blocks present","latency recorded"]}}
```

### Response Blocks (ON)
```json
{"block_1_policy":{"kind":"policy","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"test","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"rules":["meta-only input required","no raw prompt/text/content accepted","fail-closed on unknown keys"]},"block_2_plan":{"kind":"plan","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"test","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"steps":["validate meta schema","generate deterministic blocks","emit signed manifest for artifacts"]},"block_3_checks":{"kind":"checks","meta":{"request_id":"proof_test","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"test","device_class":"web","client_version":"test","ts_utc":"2026-01-29T00:00:00Z"},"checks":["forbidden keys absent","exactly 3 blocks present","latency recorded"]}}
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
        "model_id": "test",
        "device_class": "web",
        "client_version": "test",
        "ts_utc": "2026-01-29T00:00:00Z"
      },
      "rules": [
        "meta-only input required",
        "no raw prompt/text/content accepted",
        "fail-closed on unknown keys"
      ]
    },
    "block_2_plan": {
      "kind": "plan",
      "meta": {
        "request_id": "proof_test",
        "intent": "ALGO_CORE_THREE_BLOCKS",
        "model_id": "test",
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
        "model_id": "test",
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
  "manifest": {
    "sha256": "4eedc49ff75fd36c5dcb4d87820e2294ded81d652d1c77906cf71494498cf83f"
  },
  "signature": {
    "b64": "mTl8QcVS/eyIHZ3ifQVFUvxA8kNr5ytgd9KYV++KZ3xZstQ5hWY0Z6PEJZeq/KwPpHpLKEvnro3etVyeQ97uBg==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQXVEVnhhOXJ2czRwY3NNbjdxQ1N1R2pXNEM5MERLeE5GL1RQZm5OWEtGd1E9Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
    "mode": "dev"
  }
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
        "model_id": "test",
        "device_class": "web",
        "client_version": "test",
        "ts_utc": "2026-01-29T00:00:00Z"
      },
      "rules": [
        "meta-only input required",
        "no raw prompt/text/content accepted",
        "fail-closed on unknown keys"
      ]
    },
    "block_2_plan": {
      "kind": "plan",
      "meta": {
        "request_id": "proof_test",
        "intent": "ALGO_CORE_THREE_BLOCKS",
        "model_id": "test",
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
        "model_id": "test",
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
  "manifest": {
    "sha256": "54bb9a4bf1c8382eaa81e90c1ae19f44004d40a169c4197cfa63b9ca6d670328"
  },
  "signature": {
    "b64": "4a5JugwW1DHh89jO/zTnBidRVtCHKxklA5Qqs2N3+5a/3CM8NnjYfDitUeRDlJftPr8anFIM5epN+1SldMA1CQ==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQVh0OHRHYmRmS2tHeVZFWmFQeXdBMkJrK3NFdm94WjVaRDQxalQwSE01NW89Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
    "mode": "dev"
  }
}
```

### Critical Headers (OFF)
```
X-OS-Algo-Latency-Ms: 1.961
X-OS-Algo-Manifest-SHA256: 4eedc49ff75fd36c5dcb4d87820e2294ded81d652d1c77906cf71494498cf83f
```

### Critical Headers (ON)
```
X-OS-Algo-Latency-Ms: 1.200
X-OS-Algo-Manifest-SHA256: 54bb9a4bf1c8382eaa81e90c1ae19f44004d40a169c4197cfa63b9ca6d670328
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
