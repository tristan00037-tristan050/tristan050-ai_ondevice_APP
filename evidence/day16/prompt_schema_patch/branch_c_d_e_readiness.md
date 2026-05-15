# Branch C/D/E Readiness (PR #720)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 718
- branch: B (prompt/schema)
- verdict: MEASURED_ONLY

- Branch C (gold_limit ≥ 15%): {'ratio_threshold': 0.15, 'actual': 0.0198, 'enter': False, 'note': 'gold_limit 비중이 15% 이상이면 gold review 필요'}
- Branch D (deadline_f1 < 0.90): {'deadline_f1_threshold': 0.9, 'actual': 0.8092, 'enter': True}
- Branch E (auto_apply_precision < 0.95): {'auto_apply_precision_threshold': 0.95, 'actual': 0.0, 'enter': True}
- Branch F (LoRA): ABSOLUTELY_FORBIDDEN (자문 13.5)