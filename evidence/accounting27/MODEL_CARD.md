# Butler Card 5 Accounting Classification — LoRA v2 + v3 Inference Pipeline

## Attribution

본 모델은 AI Hub 27번 기업 회계처리 기준 데이터를 활용하여 개발되었습니다.
본 데이터는 과학기술정보통신부와 한국지능정보사회진흥원의
「지능정보산업 인프라 조성」 사업의 결과물입니다.

## Scope

이 adapter는 한국 기업 회계처리 기준에 따라 거래·회계 사실을 47개 계정과목으로
분류하는 회계 분류 보조용입니다. **회계 전문가 검토를 대체하지 않습니다.**
모호한 거래, 법률·세무 판단이 필요한 거래, allowlist 밖 계정과목은
`needs_review=true`로 표시해야 합니다.

## Model

- **Base model**: Qwen3-1.7B (MLX q4_k_m, 4.501 bits/weight, 923 MB)
- **Adapter**: butler-1.7b-v3-card5-accounting-lora-v2
- **Adapter size**: 76 MB (rank 32, 16 num_layers, 1500 iters)
- **Training method**: MLX LoRA adapter fine-tuning (`mlx_lm.lora`)
- **Inference pipeline**: v3 system prompt (47 allowlist 명시) + alias 사후 매핑 (12건)

## Training Details

- Data: AI Hub 27번 라벨링 12,249건 (47 allowlist primary 매핑) + 증강 1,322건 (47계정 × 35건 합성)
- Validation: 3,260건 (hash 결정적 8:2 split, doc_name overlap 0)
- Training tokens: 1,870,755 / Peak memory: 10.115 GB
- Loss: train 0.654 → 0.567 / val 0.605 → 0.520
- Wall-clock: 45분 (M3 Max Metal)
- LoRA params: rank 32 / scale 16.0 / dropout 0.05 / lr 1e-4 / batch 4 / max_seq 1024

## Evaluation (50 cases, real_run)

| Metric | baseline | v1 | v2 | **v3** | Δ(v3-baseline) |
|---|---:|---:|---:|---:|---:|
| account_title_accuracy | 0.10 | 0.22 | 0.70 | **0.84** | **+74%p** |
| debit_credit_direction | 0.84 | 0.64 | 0.94 | **0.96** | **+12%p** |
| tax_relevance | 0.54 | 0.46 | 0.76 | **0.72** | +18%p |
| structured_json_valid_rate | 1.00 | 0.90 | 1.00 | **1.00** | 0 |
| **hallucinated_account_count** | 45 | 1 | 10 | **0** | **-45** |
| unsupported_tax_assertion | 0 | 0 | 0 | **0** | 0 |
| wrong_high_confidence_count | 45 | 34 | 15 | **8** | -37 |
| account_code_consistency | 0.00 | 0.20 | 0.62 | **0.78** | **+78%p** |

## Inference Pipeline (v3)

1. **Load**: `mlx_lm.load(MODEL, adapter_path=ADAPTER)`
2. **System prompt**: 47 allowlist 명시 + ABSOLUTE RULES (JSON-only, exact 47 명명, account_code 정합)
3. **Generate**: max_tokens=160, temp=0 (greedy)
4. **Post-process**:
   - Parse JSON object
   - `apply_alias(account_title)` — 47 allowlist 정확 매칭 또는 12-alias 매핑
   - alias 매핑 시 account_code도 정합 정정

## Alias Map (12 entries)

```
서비스매출 → 용역매출       임대수익 → 임대료수익
대출이자비용 → 이자비용     사무실 월세 → 지급임차료
재고자산상각비 → 상품매출원가  원료비 → 제품매출원가
제품비 → 상품매출원가       하도급원가 → 용역원가
개발비 → 용역원가          보험수리적손실 → 잡손실
용역수익 → 용역매출         제품원가 → 제품매출원가
```

## Constraints

- `base_model_changed = false` (base safetensors 동일)
- `tokenizer_changed = false` (tokenizer.json 동일)
- `adapter_merged_into_base = false` (mlx_lm.fuse 미실행)
- `external_send = 0` (학습·평가·sealing 전 과정 외부 송신 0)
- `raw_text_retained = false` (학습 데이터 redacted, predictions JSON-only)
- `model_execution_kind = real_run` (50건 50건 mlx_lm 실측, M-59 거짓 실측 금지 정합)

## Limitations

- **본 모델은 회계 전문가 검토를 대체하지 않습니다.**
- 모호한 거래 / 법률·세무 판단 필요 거래 / allowlist 밖 계정과목 → `needs_review=true`
- 50건 평가셋 기준 — 도메인 외 거래(부동산 개발, 금융 합성 등)는 별도 검증 필요
- AI Hub 27번 데이터는 K-IFRS·중소기업회계기준·특수회계기준 QA 형식 (B/S 중심) — Butler 47 P/L 도메인과 부분 중첩 (33% 매핑)
- 본 모델은 **47 allowlist 한정 결정적 분류기**이며, 자유 계정과목 생성 모델이 아닙니다.

## Safety Checklist (HOLD 12/12 PASS)

| HOLD | Check | Status |
|---|---|---|
| 01 | dataset_117_excluded | PASS |
| 02 | license_evidence_present | PASS (sha 7a226893…) |
| 03 | aihub_attribution_present | PASS |
| 04 | raw_text_chat_exposure_zero | PASS |
| 05 | external_send_zero | PASS |
| 06 | ip6_no_new_pipeline | PASS |
| 07 | auto_finetune_trigger_zero | PASS |
| 08 | base_model_unchanged | PASS |
| 09 | tokenizer_unchanged | PASS |
| 10 | **hallucinated_account_zero** | **PASS** |
| 11 | baseline_eval_present | PASS |
| 12 | validation_separation_present | PASS |
