# Branch D/E Readiness (PR #722, Branch B-2 결과 기준)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 720
- branch: B-2
- patch_type: over_extraction_guard
- verdict: MEASURED_ONLY

- Branch D (deadline_f1 < 0.90): {'deadline_f1_threshold': 0.9, 'actual': 0.8092, 'enter': True}
- Branch E (auto_apply_precision < 0.95): {'auto_apply_precision_threshold': 0.95, 'actual': 0.0, 'enter': True}
- Branch F (LoRA): ABSOLUTELY_FORBIDDEN (자문 정합)
- MIXED-F deadline_action_entangled count: 13