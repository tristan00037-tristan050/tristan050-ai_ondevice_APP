
## Metric Definition Correction (codex bot review, PR #745 P2)

`account_code_consistency_rate` 본 정정:
- **Old formula** (incorrect): `cc/n` — title+code 결합 카운터 본 분자 본 사용. 본 metric 의미 본 왜곡 (코드 일치만 본질 vs title+code 결합 본질).
- **New formula** (corrected): `code/n` — code 일치만 본 분자 본 사용. 본 metric 본질 정합.

본 정정 본 영향:
- account_code_consistency_rate: **0.78 → 0.80** (+0.02)
- 다른 8 metric 본 영향 **0** (independent metric)
- 절대 본질 (hallucinated_account_count=0) **유지**

본 정정 봉인 본 evidence:
- `evidence/accounting27/post_v3_eval_report_corrected.json`
- `evidence/accounting27/before_after_v2_v3_comparison_corrected.json`
