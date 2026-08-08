# 교차 트랙 승인서 v2 — 박스5 AC-12 의 회계 검토 화면 변경

승인 책임자 : 대표
문서 종류   : 교차 트랙 승인서 (서명본)
대체 대상   : 183de6d · 0929fb8 · d4e8d91 세 판을 모두 대체한다

## 1. 두 기준선을 각각 다른 칸에 적는다

integration_base_sha   afdb237e4e6e83d96a182b6c5366a2ad95949bee
provenance_base_sha    de3dd4ebaf5b3935a142b988dd61e6198aa9536d
provenance_base_tree   8c3509db047145714d2a1a84dfc76fb0a4c0fec9

두 값은 역할이 다르며 서로 같기를 요구하지 않는다.

## 2. 이 승인이 지목하는 후보

candidate_head_sha           61ba1bf48d4ce5aa62f256ef80fc84e4e8aafd04
candidate_head_tree          313f40cf35b3ee2bf7bcdd946dea9c2e1c4896c2
identity_artifact_zip_sha256 5ea7f4b5355be5f4fd96b922c87f4530ddf6625abbef22848c091b2c629e2629
identity_manifest_sha256     b59e4aacd0d3f9bdd9874c838901c1ba0506478cfb15123536e729f83b4c2e4f

위 넷 중 하나라도 바뀌면 이 승인은 그 순간 효력이 없다.

## 3. 승인하는 경로 여섯. 이 밖은 승인하지 않는다

butler-desktop/src/components/accounting_review/AccountingReviewPage.tsx
butler-desktop/src/components/accounting_review/LearnedRuleSettings.tsx
butler-desktop/src/lib/accounting_review/client.ts
butler-desktop/src/lib/accounting_review/contracts.ts
butler-desktop/src/lib/accounting_review/nativeAuthorizedRequest.test.ts
butler-desktop/src/lib/accounting_review/nativeAuthorizedRequest.ts

비교 방식은 보호 범위에 걸린 경로 집합과의 완전일치다.
부분집합도 상위집합도 허용하지 않는다.

## 4. 시각

issued_at   이 문서를 담은 Git 커밋의 committer 시각을 정본으로 한다.
            문서 안에 시각을 따로 적지 않는다. 적으면 어긋나기 때문이다.
expires_at  2026-08-12T23:59:59Z

## 5. 승인 주체와 도장

approver_login  tristan00037-tristan050
approver_id     238947383
signing_key     SHA256:q87ozBPt1b218/lngOptVPRfFpgblANbUuvlUbu8HL4
namespace       butler-approval
signature_file  docs/decisions/교차트랙승인_박스5_AC12_v2_20260805.md.sig
allowed_signers docs/decisions/allowed_signers

검사는 이 도장 지문으로만 확인한다. 문서 안 글자를 믿지 않는다.

## 6. 이 승인이 허용하지 않는 것

보호 범위 설정 변경
새 보호 경로 추가
허용 범위 확대
후보가 바꾼 파일을 보고 사후에 목록을 넓히는 것
다른 base 나 head 나 tree 로의 승계
PR 903 의 병합

## 7. 남는 한계 — 숨기지 않고 적는다

도장 열쇠가 대표 기기에 있고 암호가 걸려 있지 않다.
그 기기를 쓰는 주체는 서명할 수 있다.
사람이 한 명뿐이라 권한을 완전히 나눌 수 없다.
사람이 늘거나 고객사에 팔기 전에 반드시 나눈다.
