# Runtime Shadow Mode Proof (Output-Based)

Status: SEALED
RecordedAt(UTC): 2026-02-18T04:04:32Z
PinnedMainHeadSHA: 6326796e151853f104defc1ad787c4ab51f47da6

## Test: Shadow OFF vs ON Response Identity

### Request
```json
{
  "request_id": "proof_test",
  "intent": "ALGO_CORE_THREE_BLOCKS",
  "model_id": "demoA",
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
    "sha256": "70a210d28e121b4dcf93585b96a4a656d0265264ba98117d23285a24d8a94e22"
  },
  "signature": {
    "b64": "1f9Tpdtclq4FYiaQ/Gh3cbfT5rp9BnjgEojdOdnB6CPEyMlKa63CVmkSd6GQhHyvEBKgXaj+6zSBOHF0ym2IAQ==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQUxoL3Q0Uy85WnRyaDYwUTVoN2s3MkxXbUJhMDRQbDB6MTlyVXVZWG81Rlk9Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
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
    "sha256": "e7ade90d61456aa71fddc0d9fb0ae9bdc38a34b5526c29a7e282f6550ab1994e"
  },
  "signature": {
    "b64": "R+k3cKEJ1ONwVbQekUmDWmYFMH4g9oG2AXJAI1L8jAv/R7b4bfL6/NTwHeWMRFddgdHDAQgWcFOsYAPF4FzhAg==",
    "public_key_b64": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQVA1VmVsdlhMc09UcjFlRmFWNXZXUUx5MVc2ZEhlMUV4aHVhSWNIaHRxdW89Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=",
    "mode": "dev"
  },
  "result_fingerprint_sha256": "5278c8ced22bdd4e59aa23f9d8f4cebf2ad4aa339bfde2941716b71843b16300",
  "compute_path": "ondevice"
}
```

### Critical Headers (OFF)
```
X-OS-Algo-Latency-Ms: 2.154
X-OS-Algo-Manifest-SHA256: 70a210d28e121b4dcf93585b96a4a656d0265264ba98117d23285a24d8a94e22
```

### Critical Headers (ON)
```
X-OS-Algo-Latency-Ms: 1.238
X-OS-Algo-Manifest-SHA256: e7ade90d61456aa71fddc0d9fb0ae9bdc38a34b5526c29a7e282f6550ab1994e
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
