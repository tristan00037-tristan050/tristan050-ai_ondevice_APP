# Regex Case-Sensitivity Audit (Codex P2 — 강화 안건 12)

## metadata
- source_pr: 732
- branch: B-2G
- correction_cycle: Codex P2 (NO_ACTION_MARKER case-sensitivity)
- verdict: MEASURED_ONLY

## Codex P2 결함 본질

`NO_ACTION_MARKER` 정규식이 영어 마커 `fyi` 를 소문자로만 매칭했다.
`re.compile(r"...|fyi")` 는 대문자 `FYI` / title-case `Fyi` 를 매칭하지
못해, 해당 표기의 no-action 지시를 guard 가 놓쳤다 (latent 결함).

## 정정

```python
NO_ACTION_MARKER = re.compile(
    r"참고만|확인만|정보\s*공유만|참고\s*바랍|참고용|fyi", re.IGNORECASE)
```

- `re.IGNORECASE` flag 추가 — FYI / Fyi / fyi 모두 매칭.
- 한국어 마커(참고만/확인만/정보 공유만/참고 바랍/참고용)는 case 개념이
  없어 flag 영향 없음 — 기존 동작 그대로 유지.

## guard regex pattern case-sensitivity 검증 표준

guard 의 정규식 패턴 중 **영문 토큰을 포함**하는 패턴은 다음을 검증한다:

1. 영문 토큰은 대소문자 변형(UPPER / Title / lower)을 모두 매칭하는가.
2. `re.IGNORECASE` flag 또는 `text.lower()` 정규화 중 하나를 명시 적용.
3. 대소문자 변형 sentinel 을 의무화한다 (아래).

## 대소문자 변형 sentinel 의무

영문 토큰 포함 guard 패턴은 PR sentinel 에 다음 3종을 포함한다:

- UPPER-case 변형 → 기대 동작 일치
- Title-case 변형 → 기대 동작 일치
- lower-case 변형 → 기존 동작 유지 (회귀 차단)

본 PR sentinel #13 (FYI) / #14 (Fyi) / #15 (fyi + 한국어 마커) 가 정착
사례다.

## 측정값 영향 (정직 보고)

데이터셋 card1_evalset_v1_1_500 의 500건에 대문자 `FYI` / `Fyi` 변형은
**0건**이다. 따라서 P2 정정의 측정값 영향은 없다:

- A4 차단 20/29 (불변)
- action_fp 207 (불변)
- dangerous_over_extraction_rate 0.1915 (불변)
- strict_action_f1 0.6452 (불변)

P2 는 latent regex 정합 결함의 정정이며, 현 데이터셋에서는 분포를
바꾸지 않는다 (시나리오 1). 향후 대문자 FYI 를 포함하는 입력에서는
정정된 guard 가 올바르게 차단한다.

## 강화 안건 12번 정착

본 audit 은 강화 안건 12번 (regex case-sensitivity 정합) 의 정착
사례다. 향후 모든 regex 기반 guard PR 은 영문 토큰 패턴에 대해
대소문자 변형 sentinel 을 의무화한다 (Standard 12-F 안건 정량 기반).
