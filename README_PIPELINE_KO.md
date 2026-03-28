# Butler AI Platform — 범용 데이터 파이프라인 (AI-23)

이 번들은 업로드하신 **AI-23 합본 v3**를 기준으로 만든 알고리즘팀용 드롭인 구현입니다. 원칙은 다음 네 가지에 맞췄습니다.

- 외부 전송 없음
- fail-closed
- 재현성
- 데이터 주권

## 포함 파일

- `scripts/pipeline/collector_v2.py`
- `scripts/pipeline/cleaner_v2.py`
- `scripts/pipeline/quality_filter_v2.py`
- `scripts/pipeline/formatter_v2.py`
- `scripts/pipeline/splitter_v2.py`
- `scripts/pipeline/pipeline_runner_v2.py`
- `scripts/pipeline/pipeline_manifest_v1.py`
- `scripts/pipeline/quarantine_registry_v1.py`
- `scripts/pipeline/pipeline_verify_v2.py`
- `scripts/pipeline/run_pipeline_v2.sh`
- `tests/pipeline/*`
- `tmp/*` 검증 로그

## 빠른 시작

```bash
pip install pdfplumber python-docx pytest

find scripts/pipeline -name '*.py' | xargs python -m py_compile   && echo 'COMPILE_OK=1' | tee tmp/pipeline_compile_result.txt

python scripts/pipeline/pipeline_verify_v2.py

python -m pytest tests/pipeline/ -v | tee tmp/pipeline_unittest_result.txt

mkdir -p tmp/sample_data
cat > tmp/sample_data/test.txt <<'EOF'
대한민국 헌법 제1조는 대한민국은 민주공화국이다라고 명시하고 있습니다.
모든 권력은 국민으로부터 나옵니다.
법률은 평등하게 적용되어야 합니다.
EOF

SOURCE_DIR=tmp/sample_data OUTPUT_DIR=tmp/sample_out DRY_RUN=1   bash scripts/pipeline/run_pipeline_v2.sh
```

## 실데이터 실행

```bash
SOURCE_DIR=/data/raw OUTPUT_DIR=/data/processed DRY_RUN=0   bash scripts/pipeline/run_pipeline_v2.sh
```

## 구현 포인트

### 1) 수집기
- PDF / DOCX / TXT / JSONL / JSON / CSV 6종 지원
- SHA-256 기반 dedup 캐시 영속화
- 개별 파일 실패 시 전체 파이프라인 중단 없이 진행

### 2) 정제기
- Unicode NFC 정규화
- 전화번호 / 이메일 / 주민번호 / 카드번호 / 사업자번호 마스킹
- production 기준 한국어 비율 `0.5`
- 손실 80% 이상이면 fail-closed

### 3) 품질 필터
- hallucination 패턴 검사
- `legal` / `finance` / `medical` 규제 도메인 엄격 기준
- 4-gram duplication ratio 검사
- reject enum:
  - `score_too_low`
  - `ngram_dup_too_high`
  - `hallucination_dense`
  - `domain_policy_reject`

### 4) 포맷 변환
- `prompt` / `completion` JSONL
- `output_digest_sha256` 16-hex 생성
- tokenizer chat template 검증 hook 제공

### 5) split
- split 명칭 고정: `train`, `validation`, `test`
- digest 그룹 단위 분할로 leakage 최소화
- domain stratification 유지

### 6) orchestrator
- `dry-run` / `real-run` 분리
- quarantine registry 저장
- pipeline stats 저장

### 7) manifest
- `git_sha`
- `config_digest`
- `stage_counts`
- `elapsed_seconds`

## 지금 검증 가능한 범위

- Python 컴파일
- 구조 검증
- pytest 단위 테스트
- dry-run 실행
- shell syntax

## 지금 검증 불가 / 후속 필요

1. 실제 `/data/raw` 대용량 문서군에서의 throughput
2. 스캔 PDF의 OCR 품질 편차
3. 규제 도메인별 false positive / false negative 튜닝
4. 실제 Qwen3 tokenizer와 연결한 template smoke test
5. 운영팀 실데이터 leakage=0 증빙
6. manifest / quarantine의 장기 누적 운영 정책

## 운영 권장 사항

- `output_dir`를 날짜/배치 단위로 분리해 manifest와 quarantine을 함께 보관하십시오.
- dedup 캐시는 배치별 캐시와 글로벌 캐시를 분리하는 편이 안전합니다.
- 규제 도메인 데이터는 별도 폴더와 별도 승인 절차를 두는 것이 좋습니다.
