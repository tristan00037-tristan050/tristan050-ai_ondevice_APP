# Box5 3단계 shadow 비교 도구 — 그룹A 사용법

## 이게 뭔가요 (한 줄)
통장 엑셀을 하나 넣으면, **지금 쓰는 분류기**와 **새 분류기**가 각 거래를 어떻게 분류하는지
**나란히 비교한 표**를 만들어 줍니다. 새 분류기는 **기록만** 하고, 지금 결과는 하나도 바꾸지 않습니다.

## 왜 하나요
새 분류기를 바로 켜면, 실거래에서 잘못 분류될 경우 **회계 사고**가 날 수 있습니다.
그래서 먼저 **295건을 비교**해 보고, 안전하면 그때 켤지 결정합니다. (모델 자동선택도 이렇게
먼저 관찰하고 실측 후 켰습니다.)

## 준비물
- 통장 거래내역 파일 하나 (`.xlsx`, `.xls`, `.csv`)
- 앱이 설치된 컴퓨터(또는 저장소)

## 실행 방법 (한 줄)
```bash
python3 scripts/box5_shadow_compare.py 통장.xlsx
```
결과를 다른 폴더에 저장하려면:
```bash
python3 scripts/box5_shadow_compare.py 통장.xlsx --out 결과폴더
```
> 앱 번들 안에서 실행하려면 앱의 파이썬을 쓰면 됩니다:
> `"/Applications/Butler.app/Contents/Resources/python/bin/python3" scripts/box5_shadow_compare.py 통장.xlsx`

## 무엇이 나오나요
- `box5_shadow_compare.csv` — 엑셀로 열어서 보는 **비교표**
- `box5_shadow_compare.jsonl` — 기계가 읽는 원자료

비교표 각 줄(거래 1건):
| 칸 | 뜻 |
|---|---|
| `transaction_key` | 거래를 가리키는 **익명 키(해시)** — 실제 번호·이름 아님 |
| `legacy_status` / `legacy_account_id` | **지금 분류기** 결과 (분류됨/미분류, 계정과목) |
| `shadow_status` | **새 분류기** 결과 (AUTO_PROPOSE=자동제안 / REVIEW_REQUIRED=검토필요 / BLOCKED=차단) |
| `shadow_account_id` · `shadow_rule_id` · `shadow_rule_digest` · `shadow_reason_code` | 새 분류기가 고른 계정·규칙·사유 |
| `agreement` | 두 결과 일치도 (아래) |

`agreement` 값:
- `SAME` — 둘 다 같은 계정으로 분류
- `DIFFERENT_ACCOUNT` — 둘 다 분류했는데 계정이 다름
- `SHADOW_CLASSIFIED_LEGACY_NOT` — 새 분류기만 분류
- `SHADOW_UNCLASSIFIED_LEGACY_CLASSIFIED` — 지금 분류기만 분류(새 분류기는 검토필요로 보류)
- `BOTH_UNCLASSIFIED` — 둘 다 미분류
- `SHADOW_ERROR` — 그 거래에서 새 분류기가 실행 못함(기록만, 지금 결과엔 영향 0)

## 지금 예상되는 결과
새 분류기는 **승인된 거래처(vendor) 목록이 아직 비어 있어**, 실거래를 대부분
`REVIEW_REQUIRED`(검토필요)로 보류합니다. 즉 **함부로 자동 분류하지 않습니다.**
이건 고장이 아니라, **안전하게 보수적으로** 동작하는 것입니다. 295건에서 이 경향을
확인하는 것이 이번 검증의 목적입니다.

## 꼭 기억할 것
- 이 도구는 **기록만** 합니다. 지금 쓰는 분류 결과·엑셀은 **하나도 바뀌지 않습니다.**
- **자동 기표(장부 자동 기록)는 잠겨 있습니다**(JOURNAL_AUTO_POST_ALLOWED=NO). 새 분류기가
  무엇을 제안해도 자동으로 장부에 쓰이지 않습니다.
- 원문·상호명·계좌번호는 저장하지 않습니다(필요한 것만 해시로).
