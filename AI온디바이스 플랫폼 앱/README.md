# AI온디바이스 플랫폼 앱 — App Core Starter (Web Core 4.17 Baseline)

이 스타터 번들은 **웹 코어 4.17 기준선**의 QuickCheck/Policy/Gate/Redaction/Bundle 철학을
**앱 코어 프로젝트**에 그대로 이식할 수 있도록 준비된 템플릿입니다.

## 공통 기준(반드시 준수)
- **메트릭 라벨**: `decision|ok`만 사용(화이트리스트).
- **내부 게이트웨이 전용** 호출, **/ops 비노출**.
- **Policy Gate**: `severity=block`은 CI 실패, `--strict-warn` 시 `warn`도 실패로 승격 가능.
- **리포트 순서**: Status → Diff → Policy → Notes 고정, JSON 키 순서도 `status, diff, policy, notes, raw` 고정.
- **Observability Δ%**: EPS(1e-6) 가드 + ±500% 클램프(표현 상한) 유지.
- **PR Redaction**: 규칙을 JSON으로 외부화 + **80% 과도 마스킹 가드**.

## 포함물
- `contracts/` : 정책/리포트/마스킹 **스키마(계약)**.
- `configs/`   : 정책 예시(JSON).
- `redact/`    : 마스킹 규칙 예시(JSON).
- `scripts/ops/` : QC Markdown 변환, 정책 게이트, 증빙 번들 스크립트(ESM, Node.js).
- `docs/`      : 웹→앱 포팅 가이드.
- `examples/`  : QC 스냅샷 예시(JSON).
- `metadata/VERSION` : `web-core-4.17.0` 기준선 메타.

## 사용 예시
```bash
# 1) 예시 스냅샷 → MD
node scripts/ops/app_quickcheck_md.mjs examples/qc_snapshot.example.json > qc.md

# 2) 정책 게이트(경고 미승격)
node scripts/ops/app_quickcheck_gate.mjs \  --qc examples/qc_snapshot.example.json \  --policy configs/webcore_qc_policy.example.json

# 3) 증빙 번들 생성(+meta/checksums, zip 옵션 지원)
node scripts/ops/app_quickcheck_bundle.mjs \  --qc ./examples/qc_snapshot.example.json \  --md ./qc.md \  --out ./bundles/qc_bundle_demo \  --base-url https://internal-gw \  --policy-version v1 \  --app-version 0.1.0 \  --zip
```