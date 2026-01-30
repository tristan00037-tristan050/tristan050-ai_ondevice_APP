# Runtime Shadow Mode Proof (Output-Based)

Status: SEALED
RecordedAt(UTC): 2026-01-30T01:38:17Z
PinnedMainHeadSHA: 1fc8428288af2996fa31ab8a46c78c934d7ff715

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
    "sha256": "88b4039e7a9e498f26e4f038d2f692ba018bd5134c77050cfed91c8686b1b9ac"
  },
  "signature": {
    "b64": "eeADnVoBKW++PUXeaGpVm3Yzi5puIFu3CsmzatlVrFx16iuMn4q49gGUqc6esNEUnd+2jX184tcG3D5AT3E/Bw==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQVlwdEhsQ3Vucy9TQnFJQ0lGNEtpVS81dkJIMjh2d0w5cmY1ZmlKNG00L289Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
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
    "sha256": "abe99d6641f5ec61179690407b8c9e86e701bd127de04ac5c80fe88982bd318c"
  },
  "signature": {
    "b64": "yf4ISAwdQmb9sEhBoKhyyTZ4lE2U/GtZ5a82yTeUsMr05ANPsBfpAj6bGrbuiOzhwbLqgzor0DNVSP6uMSmVBw==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQVFOeXl4V3JpNWh2djlEd2U3VDI5clRSMTJ3LzRzQ3NWNzZrQ0xNMXBCd0k9Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
    "mode": "dev"
  }
}
```

### Critical Headers (OFF)
```
X-OS-Algo-Latency-Ms: 1.256
X-OS-Algo-Manifest-SHA256: 88b4039e7a9e498f26e4f038d2f692ba018bd5134c77050cfed91c8686b1b9ac
```

### Critical Headers (ON)
```
X-OS-Algo-Latency-Ms: 1.196
X-OS-Algo-Manifest-SHA256: abe99d6641f5ec61179690407b8c9e86e701bd127de04ac5c80fe88982bd318c
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
