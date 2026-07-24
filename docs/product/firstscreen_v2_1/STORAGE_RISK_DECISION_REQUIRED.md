# 저장 위험 승인 필요

다음 항목은 코드 PASS로 간주하지 않는다. 대표 또는 지정 보안 책임자가 `contracts/home_v2_1/storage_risk_acceptance.schema.json`에 맞는 만료 기한·검토 트리거·서명 digest를 제출해야 한다.

- 대화 제목과 FTS title index의 plaintext 유지
- 고급 read concurrency
- audit HMAC/hash chain
- 비 macOS credential provider 확장
- 자동 key recovery/rekey/re-encryption
- bundle 성능 budget

현재 signed approval은 없다. 따라서 관련 finding은 `BLOCKED_EXTERNAL`이며 `ACCEPTED_RISK_OUT_OF_SCOPE`로 가장하지 않는다. message content는 AES-GCM 암호화를 유지하고 app-data owner/mode/symlink guard를 적용한다.
