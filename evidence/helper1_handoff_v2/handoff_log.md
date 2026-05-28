# 도우미1_기억 인계 로그

## 인계 기준일: 2026-05-28

## 작업 이력

| 단계 | 내용 | 결과 |
|---|---|---|
| Track 0 Option B | 59 chunk 정밀 재청킹 (156,520 variant) | NO_PROGRESS (MeCab 없이 SHA 불일치) |
| Stage 1 | heading-aware recursive chunker v1.1 (max_chars=1800) | 1295 chunks / 100 docs |
| Stage 2 | BGE-M3 임베딩 (1295×1024) + BM25 (vocab 6825) | 319초 완료 |
| Stage 3 | find() SDK: Dense→BM25→RRF 파이프라인 | 구현 완료 |
| Stage 4 | RAG: butler-1.7b-v4-rt-q4_k_m llama_cpp 0.3.21 | 로드 완료 |
| Stage 5 | Smoke test 3건 | PASS 3/3 (p50=13s, p95=16s) |
| Stage 6 | 인계 폴더 패키지 + evidence ZIP | 완료 |

## 정직 표명

- **chunk 수**: 목표 375 → 실제 1295 (heading 세밀 분리로 증가)
- **BGE-reranker**: weights 미다운로드 → RRF top-5 사용 (reranker 단계 스킵)
- **FAISS**: 미설치 → numpy inner product 사용 (1295 chunks 규모에서 충분)
- **LLM 답변 품질**: butler-1.7b-v4-rt 프롬프트 형식 불일치로 반복 패턴 발생 가능 → 프롬프트 포맷 튜닝 권장
- **production_claim_allowed**: false 유지

## 개선 과제

1. BGE-reranker-v2-m3 weights 다운로드 (`huggingface-cli download BAAI/bge-reranker-v2-m3`)
2. butler-1.7b 프롬프트 형식 확인 및 수정
3. FAISS 설치 (`pip install faiss-cpu`) 후 HNSW 인덱스로 전환
4. MeCab 설치 후 59 missing chunk 재시도

## SHA 봉인

| 파일 | SHA-256 |
|---|---|
| chunks_v2 | sha256:928ac0cde48b515c... |
| embeddings_v2 | sha256:84672a39300ad9c8... |
| bm25_v2 | sha256:1cf8f19e0862ad68... |
| manifest_v2 | sha256:9ae7482079a37a2a... |
| sdk | sha256:737b900d4cf61d88... |
| mvp_seal | sha256:3044622dcda23e87... |
