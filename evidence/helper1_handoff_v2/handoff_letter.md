# 도우미1_기억 인계서

**한 줄 정의**: (주)에이티링크 사내 문서 100건 기반 RAG 검색·답변 시스템

## 사용법

```python
from sdk.memory_helper import find, ask

# 검색만
results = find("Phase 5.4 운영 안정성 변경 사항은?", top_k=5)
for r in results:
    print(r["chunk_id"], r["chunk_text"][:100])

# RAG 답변
result = ask("Helm 배포 순서는?")
print(result["answer"])
print(result["sources"])
```

## 파이프라인

```
질문 → BGE-M3 Dense(top-100) + BM25(top-100)
      → RRF fusion(top-30)
      → [BGE-reranker*] top-5
      → butler-1.7b-v4-rt RAG 답변
```
*BGE-reranker-v2-m3: 현재 weights 미다운로드 → RRF 결과 직접 사용

## 필수 경로

| 항목 | 경로 |
|---|---|
| BGE-M3 | `/private/tmp/bge_m3_combined` |
| butler GGUF | `/Volumes/T7 Shield/학습모델/butler-1.7b-v4-rt/butler-1.7b-v4-rt-q4_k_m.gguf` |
| chunks_v2 | `~/Desktop/기억도우미/runtime/private/helper1_chunks_v2.local.jsonl` |
| 임베딩 | `~/Desktop/기억도우미/runtime/private/helper1_embeddings_v2.npy` |
| BM25 | `~/Desktop/기억도우미/runtime/private/helper1_bm25_v2.pkl` |

## 한계

1. BGE-reranker-v2-m3 weights 미설치 → reranking 단계 스킵 (RRF top-5 사용)
2. FAISS 미설치 → numpy inner product (속도 저하 없음, 375 chunks 규모에서)
3. production_claim_allowed = false (사내 beta 수준)
4. 소스 문서 100건 고정 → 신규 문서 추가 시 빌드/인덱스 재실행 필요

## 재빌드 방법

```bash
python3 ~/Desktop/기억도우미/scripts/mvp_stage1_build_chunks_v2.py
python3 ~/Desktop/기억도우미/scripts/mvp_stage2_embed_index.py
python3 동작확인/smoke_test.py
```
