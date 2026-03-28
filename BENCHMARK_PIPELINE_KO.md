# BENCHMARK_PIPELINE_KO

## 요약

AI-23는 단순한 파일 정리 스크립트가 아니라, **기업 내부 문서를 외부 전송 없이 수집 → 정제 → 검증 → 포맷화 → split → manifest**까지 완결하는 온프레미스 데이터 파이프라인입니다. 2026 기준으로 경쟁력 있는 구현은 다음 다섯 축을 동시에 가져가야 합니다.

1. 문서 파싱 품질
2. PII/민감정보 보호
3. 데이터 품질 검증
4. 대규모 dedup / provenance
5. 모델 투입 형식의 일관성

## 비교 대상과 반영 방향

### Docling
- 공식 문서: Docling은 PDF/DOCX/PPTX/XLSX/HTML/이미지 등 다양한 포맷을 지원하고, advanced PDF understanding 및 lossless JSON export를 제공합니다.
- 반영 방향:
  - 현재 번들의 collector는 6개 포맷에 집중
  - 후속 단계에서 Docling을 optional backend로 연결하면 PDF table / reading order 품질을 크게 개선할 수 있습니다.

### Unstructured
- 공식 리포지토리: Unstructured는 문서를 clean structured formats로 바꾸는 open-source ETL이며, production-grade partitioning / enrichments / chunking을 강조합니다.
- 반영 방향:
  - 현재 번들은 chunking 대신 raw-to-training JSONL 중심
  - 후속 단계에서 chunking 정책과 enrichment metadata를 추가할 수 있습니다.

### Microsoft Presidio
- 공식 문서: Presidio는 NER / regex / rules / checksum 기반의 PII recognizer와 anonymizer, image redactor, structured data 처리까지 제공합니다.
- 반영 방향:
  - 현재 cleaner는 regex 5종 fail-closed
  - 후속 단계에서 Presidio Analyzer/Anonymizer를 optional plugin으로 연결하면 탐지 정확도를 높일 수 있습니다.

### Great Expectations
- 공식 문서: GX는 파이프라인 전반의 critical data validation과 공통 품질 언어를 제공합니다.
- 반영 방향:
  - 현재 pipeline_verify_v2.py는 lightweight smoke 검증
  - 후속 단계에서 schema assertion, split count bounds, domain ratio bounds를 GX/Pandera 스타일 계약으로 확장하는 것이 좋습니다.

### Hugging Face DataTrove
- 공식 리포지토리: DataTrove는 대규모 text processing / filtering / dedup 블록을 제공하며 local/slurm/ray executor를 지원합니다.
- 반영 방향:
  - 현재 번들은 단일 노드/로컬 중심
  - 데이터가 수백 GB 이상으로 늘어나면 minhash/signature dedup 블록으로 확장하는 것이 맞습니다.

### Hugging Face Datasets
- 공식 문서: local `csv`, `json`, `txt`, `parquet` 로딩과 `train/validation/test` split 네이밍 규약을 명확히 지원합니다.
- 반영 방향:
  - 현재 splitter는 `train/validation/test`를 강제
  - 후속 단계에서 parquet export와 dataset card 생성까지 이어갈 수 있습니다.

## OpenAI / Claude / Gemini와의 격차 축소 관점

이 파이프라인은 모델 자체가 아니라 **모델에 들어가기 전 데이터 품질 계층**입니다. 그래도 현재 선도 플랫폼들은 공통적으로 다음을 강조합니다.

- OpenAI: structured outputs, function calling, tools, conversation state
- Claude: Agent SDK, tool use, streaming, evals, prompt caching
- Gemini: structured outputs, function calling, built-in tools + custom tools combination

따라서 격차를 줄이려면 데이터 파이프라인도 아래 방향으로 진화해야 합니다.

1. 모든 변환 결과를 strict schema로 남길 것
2. quarantine reason을 enum으로 고정할 것
3. provenance(manifest, git_sha, config_digest)를 필수화할 것
4. 후속 에이전트나 학습 파이프라인이 바로 소비할 수 있는 JSONL/Parquet를 만들 것
5. 규제 도메인 reject 기준을 데이터 정책으로 코드화할 것

## 다음 단계 우선순위

1. Docling optional parser backend
2. Presidio optional PII backend
3. Pandera/GX 스타일 schema contract
4. Parquet export + dataset card
5. MinHash near-duplicate mode
6. OCR 스캔 PDF 전용 lane
