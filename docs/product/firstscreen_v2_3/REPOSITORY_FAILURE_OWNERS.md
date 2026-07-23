# 저장소 회귀 실패 소유 트랙

v2.2 제출 기준 repo-wide 결과는 3,055 pass / 81 fail / 32 skip / collection error 0이다.
v2.3 재실행 결과는 3,064 pass / 동일한 81 fail / 32 skip / collection error 0이다.
아래는 실패를 PASS로 바꾸지 않고 실제 기능 정본에 귀속한 triage다.

| 범주 | 소유 트랙 | FirstScreen 판정 |
|---|---|---|
| policy bootstrap·admin role registry fixture | company policy / admin onboarding | 기존 회귀, 별도 폐쇄 필요 |
| Box4/Box6 grammar·route/error schema | Box4/6 기능 트랙 | 기존 회귀, 별도 폐쇄 필요 |
| missing model adapter·optional grammar asset | model runtime·algorithm integration | 명시 marker·truthful skip 계약 필요 |
| router/role registry drift | onboarding / learning | 기존 회귀, 별도 폐쇄 필요 |
| legacy static security scan | security platform | semantic verifier 전환 필요 |

FirstScreen 변경으로 새로 발생한 실패는 0이어야 하며, 전체 저장소 0 fail 조건 자체는 삭제하지 않는다.
