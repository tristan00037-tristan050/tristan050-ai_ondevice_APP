# Runtime Shadow Mode Proof (Output-Based)

Status: SEALED
RecordedAt(UTC): 2026-02-10T03:36:22Z
PinnedMainHeadSHA: 33963011f86105b633ba9b5ff2374de058f54bfa

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
    "sha256": "005f5d912882f2f659d9b8a118413ae843b4d35b400030ca3b778f27474050ef"
  },
  "signature": {
    "b64": "yFnSNpiRNjOATs+gjAXsXeOEVLNLLmhQlAllf+VVlSEyd1mhQXfWJrhNQIf8/gddMD/8AAPn7+qD6B2qZOeaBg==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQTcrWERoR001eTNkaDl3WURBQTBqZkwyd2pBbEw1ak9TUEc3d0VVdUdsa009Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
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
    "sha256": "ed4aa7f3f0c4f6e1e35cad101d918bfcc3c20b0bd451b9f8fc8ba75827c9c850"
  },
  "signature": {
    "b64": "yinl6unKEngQ7KNgN/pEIS8dHdebGUjq3uaQbYGNFu3/8qPsnggT2+hJhbSsbX/HgqL4VOXJ/jKiBTa4BpXtAQ==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQWpFdGZ2TXVKRHlMU091TnlrZm82RWxaY0xhT2c1Vk90TWdGR2ttZXJ1aE09Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
    "mode": "dev"
  },
  "result_fingerprint_sha256": "5278c8ced22bdd4e59aa23f9d8f4cebf2ad4aa339bfde2941716b71843b16300",
  "compute_path": "ondevice"
}
```

### Critical Headers (OFF)
```
X-OS-Algo-Latency-Ms: 1.229
X-OS-Algo-Manifest-SHA256: 005f5d912882f2f659d9b8a118413ae843b4d35b400030ca3b778f27474050ef
```

### Critical Headers (ON)
```
X-OS-Algo-Latency-Ms: 1.173
X-OS-Algo-Manifest-SHA256: ed4aa7f3f0c4f6e1e35cad101d918bfcc3c20b0bd451b9f8fc8ba75827c9c850
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
