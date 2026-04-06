# 토크나이징 캐시 운영 규칙 (SSOT)

## 캐시 저장 위치
| 위치 | 경로 | 비고 |
|---|---|---|
| 네이버 클라우드 스토리지 | butler-data (ID: 134279703) `/data/토크나이징_v2/` | KR-2 존, CB2 600GB |

## 캐시 키 구성 요소
- file_size (os.path.getsize)
- file_mtime (os.path.getmtime)
- dataset_len (len(dataset))
- tokenizer.name_or_path
- max_length
- split_name
- cache_schema_version: v1

## 새 서버 부팅 시 절차
1. 네이버 클라우드 콘솔에서 butler-data(134279703) → 새 서버에 연결
2. `mkdir -p /data && mount /dev/vdb /data`
3. `du -sh /data/토크나이징_v2/` → 49G 확인
4. 학습 스크립트에 `--tokenize-cache-dir /data/토크나이징_v2` 전달

## 정상 동작 로그
- 캐시 HIT: `TOKENIZE_CACHE_HIT_SPLIT=train`, `TOKENIZE_CACHE_HIT_SPLIT=eval`
- 캐시 MISS: `TOKENIZE_CACHE_MISS_SPLIT=train`, `TOKENIZE_CACHE_MISS_SPLIT=eval`
- 캐시 저장: `TOKENIZE_CACHE_SAVE_SPLIT=train`, `TOKENIZE_CACHE_SAVE_SPLIT=eval`

## smoke 검증 명령 (새 서버 부팅 후 반드시 실행)
```bash
CUDA_VISIBLE_DEVICES=0 python3 scripts/ai/finetune_qlora_small_v1.py \
  --train-file /root/processed/train.jsonl \
  --eval-file /root/processed/validation.jsonl \
  --output-dir /root/output/butler_smoke \
  --smoke-steps 20 \
  --max-train-samples 2048 \
  --max-eval-samples 256 \
  --tokenize-cache-dir /data/토크나이징_v2 \
  2>&1 | tee /root/smoke.log
grep "TOKENIZE_CACHE_HIT_SPLIT" /root/smoke.log
```
반드시 `TOKENIZE_CACHE_HIT_SPLIT=train` 과 `TOKENIZE_CACHE_HIT_SPLIT=eval` 두 줄이 출력되어야 함.
