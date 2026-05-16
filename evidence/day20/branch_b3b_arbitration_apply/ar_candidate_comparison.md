# AR Candidate Comparison (Branch B-3B, 자문 1.4)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 725
- branch: B-3B
- patch_type: arbitration_apply
- verdict: PATCH_CONTINUE

## baseline (no arbitration): f1=0.6182 fp=234

## AR 후보
- AR-2: f1=0.6173 fp=235 a1_recover=0 a3_recover=0
- AR-4: f1=0.6182 fp=234 a1_recover=0 a3_recover=0
- AR-2+AR-4: f1=0.6173 fp=235 a1_recover=0 a3_recover=0

## selected: AR-4