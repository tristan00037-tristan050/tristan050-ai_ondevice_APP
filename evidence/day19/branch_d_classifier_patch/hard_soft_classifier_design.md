# HARD ↔ SOFT Classifier Design (Branch D, 자문 5.1)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 723
- branch: D
- patch_type: deadline_classifier
- verdict: MEASURED_ONLY

## HARD markers
- 명시 날짜 (M월 D일 / YYYY-MM-DD)
- 명시 시각 (HH:MM / N시)
- 요일 + 까지 (이번 주 금요일까지 → HARD override)
- 내일까지 / 오늘까지 / 모레까지 / 전까지

## SOFT markers
- 오늘 중 / 내일 중 / 이번 주 안에 / 이번 주 중
- 다음 주 안에 / 가능하면 / 조만간 / 이번 달 안에

## 경계 규칙
- HARD override (요일+까지) 최우선
- HARD + SOFT 동시 매칭 → HARD (명시 시점 존재)

## 측정: HARD↔SOFT confusion 14 → 5