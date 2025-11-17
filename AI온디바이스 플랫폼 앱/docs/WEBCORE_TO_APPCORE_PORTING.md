# Web → App Core 포팅 가이드

이 문서는 웹 코어(4.17)에서 정립된 QuickCheck/Policy/Gate/Bundle/Redaction 구조를
앱 코어(온디바이스)까지 동일하게 이식하기 위한 최소 절차를 설명합니다.

## 1) 공통 계약 복제
- `contracts/`의 스키마(JSON Schema)와 `configs/webcore_qc_policy.example.json` 정책 예시를 앱 레포에 복제합니다.
- 정책은 런타임에서 스키마 검증을 통과해야 합니다(필수 필드: policy_version, created_at, rules[].severity).

## 2) 스냅샷 수집
- 앱 코어에서 6개 인디케이터(API/JWKS/Holidays/Observability/ICS/LH)를 수집하여 QuickCheck 스냅샷(JSON)을 생성합니다.
- 기본 구조는 `examples/qc_snapshot.example.json`을 참고하세요.

## 3) 게이트와 리포트
- `scripts/ops/app_quickcheck_gate.mjs`로 정책 게이트(CI) 수행.
- `scripts/ops/app_quickcheck_md.mjs`로 QC MD 리포트 생성 → PR 코멘트/위키에 사용.

## 4) 증빙 번들
- `scripts/ops/app_quickcheck_bundle.mjs`로 bundle_meta.json, checksums.txt 포함 번들 생성(+zip 옵션).
- audit/증빙 요구에 대비해 번들을 아티팩트로 보관하세요.

## 5) Redaction
- `redact/redact_rules.example.json`을 시작점으로 환경/고객별 민감정보 마스킹 규칙을 추가하세요.
- 과도 마스킹(≥80%) 가드 규칙을 유지하세요.

## 6) DoD
- 정책 스키마 검증 PASS
- 게이트(블록 규칙 위반 시 CI 실패) 동작 확인
- 리포트 순서/키 순서 합치
- 번들에 메타/체크섬 포함
- 라벨 정책: decision|ok만 사용
- /ops 비노출, 내부 게이트웨이 전용