from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
import tempfile


SAMPLE = (
    "대한민국 헌법 제1조는 대한민국은 민주공화국이다라고 명시하고 있습니다.\n"
    "모든 권력은 국민으로부터 나오며 국민의 기본권은 헌법에 의해 보장됩니다.\n"
    "법률의 적용은 평등해야 하며 누구도 법 앞에서 차별받아서는 안 됩니다."
)


class _DummyTokenizer:
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, enable_thinking=False):
        if enable_thinking is not False:
            raise RuntimeError("enable_thinking must be false")
        return "ok"


def verify() -> dict:
    report: list[dict] = []
    skipped: list[dict] = []
    required = [
        "scripts/pipeline/__init__.py",
        "scripts/pipeline/collector_v2.py",
        "scripts/pipeline/cleaner_v2.py",
        "scripts/pipeline/quality_filter_v2.py",
        "scripts/pipeline/formatter_v2.py",
        "scripts/pipeline/splitter_v2.py",
        "scripts/pipeline/pipeline_runner_v2.py",
        "scripts/pipeline/pipeline_manifest_v1.py",
        "scripts/pipeline/quarantine_registry_v1.py",
        "scripts/pipeline/run_pipeline_v2.sh",
    ]

    for relpath in required:
        ok = Path(relpath).exists()
        report.append({"file": relpath, "ok": ok})
        print(f"[{'PASS' if ok else 'FAIL'}] {relpath}")

    from scripts.pipeline.cleaner_v2 import DataCleaner
    cleaner = DataCleaner(min_korean_ratio=0.5)
    clean_result = cleaner.clean(SAMPLE)
    ok = clean_result.passed and clean_result.is_korean and clean_result.korean_ratio >= 0.5
    report.append({"check": "cleaner_korean_0.5", "ok": ok, "ratio": clean_result.korean_ratio})
    print(f"[{'PASS' if ok else 'FAIL'}] cleaner 한국어(0.5 기준)")

    pii_text = "연락처: 010-1234-5678, 이메일: test@example.com"
    pii_result = cleaner.clean(pii_text + " 한국어 문장입니다. 테스트입니다.")
    ok = "[PHONE]" in pii_result.text and "[EMAIL]" in pii_result.text
    report.append({"check": "pii_masking", "ok": ok})
    print(f"[{'PASS' if ok else 'FAIL'}] PII 마스킹")

    from scripts.pipeline.quality_filter_v2 import QualityFilter
    quality_result = QualityFilter().evaluate(SAMPLE)
    ok = quality_result.score > 0.3
    report.append({"check": "quality_score", "ok": ok, "score": quality_result.score})
    print(f"[{'PASS' if ok else 'FAIL'}] quality score: {quality_result.score:.3f}")

    legal_hallucinated = "이 판결은 법적으로 추정되며 판결이 내려진 것으로 보인다."
    strict_result = QualityFilter().evaluate(legal_hallucinated)
    ok = strict_result.reject_reason in {"hallucination_dense", "domain_policy_reject"}
    report.append({"check": "restricted_domain_strict_policy", "ok": ok, "reason": strict_result.reject_reason})
    print(f"[{'PASS' if ok else 'FAIL'}] 규제 도메인 엄격 기준")

    from scripts.pipeline.formatter_v2 import DataFormatter
    formatter = DataFormatter()
    record = formatter.format_document(SAMPLE, "legal", 0.8, "test")
    ok = record is not None and len(record.output_digest_sha256) == 16
    report.append({"check": "formatter_digest", "ok": ok})
    print(f"[{'PASS' if ok else 'FAIL'}] formatter + digest")

    template_ok = formatter.validate_template(_DummyTokenizer())
    report.append({"check": "template_validate", "ok": template_ok})
    print(f"[{'PASS' if template_ok else 'FAIL'}] tokenizer template 검증")

    from scripts.pipeline.splitter_v2 import DataSplitter
    sample_records = [
        {
            "domain": "legal" if i < 10 else "finance",
            "output_digest_sha256": f"hash{i}",
            "prompt": f"q{i}",
            "completion": f"a{i}",
            "quality_score": 0.8,
            "source": "test",
        }
        for i in range(20)
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        split_result = DataSplitter().split(sample_records, tmpdir)
        ok = split_result["leakage_count"] == 0
        report.append({"check": "splitter_leakage", "ok": ok, "leakage_count": split_result["leakage_count"]})
        print(f"[{'PASS' if ok else 'FAIL'}] splitter leakage: {split_result['leakage_count']}건")

    all_pass = all(item.get("ok", False) for item in report)
    Path("tmp").mkdir(parents=True, exist_ok=True)
    Path("tmp/pipeline_verify_result.json").write_text(
        json.dumps({"report": report, "all_pass": all_pass, "skipped": skipped}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if all_pass:
        print("PIPELINE_VERIFY_OK=1")
    return {"all_pass": all_pass}


if __name__ == "__main__":
    verify()
