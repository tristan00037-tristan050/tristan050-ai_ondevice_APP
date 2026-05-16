# Evaluation PR Template Update — Standard 10

## metadata
- source_pr: 729
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## 갱신 대상

`.github/PULL_REQUEST_TEMPLATE/eval_pr.md` — 기존 평가 PR template (PR #728
정착)에 Standard 10 체크리스트 섹션 추가. 기존 STATUS / Standard 9 /
Standard 12 / 회귀 monitor / sentinel / forbidden grep / 표준 1~12 점검
섹션은 불변.

## 추가 섹션

```
## Standard 10 — Strict Policy Base Drift
- [ ] metric threshold 변경 0건
- [ ] label guide 변경 시 version bump (SemVer MAJOR.MINOR.PATCH)
- [ ] before/after comparison 표 포함 (정밀 patch PR)
- [ ] policy drift report 작성 — drift 5%↑ PATCH_CONTINUE / 20%↑ HOLD
- [ ] old policy vs new policy 비교 가능성 보증
- [ ] CI guard check_standard_10.py 통과
```

## 삽입 위치

Standard 12 섹션과 회귀 monitor 섹션 사이 — 표준 번호 순서 정합.

## 정합 원칙

- 정밀 patch PR (Branch C-lite / D-2 등) 은 before/after comparison 표
  필수, drift 5% 이상 시 verdict 를 PATCH_CONTINUE / HOLD 로 한정.
- 정착/문서 PR 은 metric threshold·label guide 미변경이므로 해당 항목
  자동 충족.

## verdict: MEASURED_ONLY
