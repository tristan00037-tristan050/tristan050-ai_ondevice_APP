# P1 Hardening SEALED Record (2026-01-31)

Status: PASS (SEALED)

이 문서는 P1(공급망 DSSE / 업데이트 영속 / 실 DB 어댑터) 완료를 증빙(출력/CI required checks)으로 고정하여
재논쟁/드리프트를 방지하기 위한 단일 정본입니다.

## 기준선 검증 (main)

```bash
bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?"
```

기대: EXIT=0

## P1-1 SUPPLYCHAIN-DSSE

PR #221 (DSSE attestation verify + actor identity)

PR #222 (GH_TOKEN 봉인 + 증빙 안정화)

Required check: product-verify-supplychain (green)

## P1-2 UPDATE-PERSIST (UPDATE-02)

PR #223 (max_seen_version persisted + atomic anti-rollback)

Required check: product-verify-model-registry (green)

Verify script (optional local): scripts/verify/verify_update_max_seen_version_persist.sh

## P1-3 STORE-REAL (STORE-02)

PR #224 (sql.js DBStore real adapter + contract parity)

Required check: product-verify-model-registry (green)

Verify script (optional local): scripts/verify/verify_svr03_store_parity.sh

## 운영 규율(고정)

- PASS 판정은 "required checks green + main baseline EXIT=0"로만 인정한다.
- merge_group 경로를 포함하며, job-level if로 skip/bypass 경로를 만들지 않는다.

