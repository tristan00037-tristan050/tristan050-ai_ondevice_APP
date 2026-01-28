# ALGO-CORE-04 Runtime Smoke Proof (SEALED)

Generated_utc: 2026-01-28T05:40:21Z
Base_sha: 27f0981
Endpoint: POST /v1/os/algo/three-blocks
Mode: dev (ephemeral key allowed)

## Response headers (captured)
```
HTTP/1.1 200 OK
X-Request-Id: e1265991-4389-47da-bdce-f7ac9546f905
Cross-Origin-Opener-Policy: same-origin
Origin-Agent-Cluster: ?1
Referrer-Policy: no-referrer
Strict-Transport-Security: max-age=15552000; includeSubDomains
X-Content-Type-Options: nosniff
X-DNS-Prefetch-Control: off
X-Download-Options: noopen
X-Frame-Options: SAMEORIGIN
X-Permitted-Cross-Domain-Policies: none
X-XSS-Protection: 0
RateLimit-Policy: 300;w=60
RateLimit-Limit: 300
RateLimit-Remaining: 299
RateLimit-Reset: 60
X-OS-Algo-Latency-Ms: 1.285
X-OS-Algo-Manifest-SHA256: 59ab95f3e650e4c78c7881679940e09e6e0ff3fd4fb72a744c6af08da55a1eab
Content-Type: application/json; charset=utf-8
Content-Length: 1327
ETag: W/"52f-TmiMxKDb2FPcxGM4Le00LlqBRFA"
Date: Wed, 28 Jan 2026 05:40:21 GMT
Connection: keep-alive
Keep-Alive: timeout=5

```

## Response body (captured)
```json
{"ok":true,"blocks":{"block_1_policy":{"kind":"policy","meta":{"request_id":"req_demo","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"algo-core-demo","device_class":"web","client_version":"0.0.0-dev","ts_utc":"2026-01-28T00:00:00Z"},"rules":["meta-only input required","no raw prompt/text/content accepted","fail-closed on unknown keys"]},"block_2_plan":{"kind":"plan","meta":{"request_id":"req_demo","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"algo-core-demo","device_class":"web","client_version":"0.0.0-dev","ts_utc":"2026-01-28T00:00:00Z"},"steps":["validate meta schema","generate deterministic blocks","emit signed manifest for artifacts"]},"block_3_checks":{"kind":"checks","meta":{"request_id":"req_demo","intent":"ALGO_CORE_THREE_BLOCKS","model_id":"algo-core-demo","device_class":"web","client_version":"0.0.0-dev","ts_utc":"2026-01-28T00:00:00Z"},"checks":["forbidden keys absent","exactly 3 blocks present","latency recorded"]}},"manifest":{"sha256":"59ab95f3e650e4c78c7881679940e09e6e0ff3fd4fb72a744c6af08da55a1eab"},"signature":{"b64":"JtEZktjkbpMtBBsLq9+hG85Jo5YeKVcoc+5Am5DYPB84rD11wRYLyvqcdlwKt9Rbm9kcaav4npKhRqnGFFsgCg==","public_key_b64":"LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUNvd0JRWURLMlZ3QXlFQWJNMjhFemN6Mnl1R1VTUTlPc3QzalU4dzdXRFpzVHBuT1hnSkp0VEhOL0U9Ci0tLS0tRU5EIFBVQkxJQyBLRVktLS0tLQo=","mode":"dev"}}```

## Output-based checks
- ok=true
- blocks count == 3
- manifest.sha256 present
- signature.b64 and signature.public_key_b64 present
