from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json
import time

from scripts.pipeline.cleaner_v2 import DataCleaner
from scripts.pipeline.collector_v2 import DataCollector
from scripts.pipeline.formatter_v2 import DataFormatter
from scripts.pipeline.pipeline_manifest_v1 import create_manifest, save_manifest
from scripts.pipeline.quality_filter_v2 import QualityFilter
from scripts.pipeline.quarantine_registry_v1 import QuarantineRegistry
from scripts.pipeline.splitter_v2 import DataSplitter


DEFAULT_CONFIG = {
    "min_korean_ratio": 0.5,
    "min_quality_score": 0.3,
    "restricted_min_quality_score": 0.5,
    "max_ngram_dup": 0.4,
    "split_names": ["train", "validation", "test"],
    "external_transfer": False,
    "fail_closed": True,
}


def run_pipeline(source_dir: str, output_dir: str, dry_run: bool = False) -> dict:
    start = time.time()
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"source_dir not found: {source_dir}")

    quarantine = QuarantineRegistry(output_dir)
    stats: dict = {
        "source_dir": source_dir,
        "output_dir": output_dir,
        "dry_run": bool(dry_run),
        "stages": {},
    }

    print("[1/7] 데이터 수집 중...")
    collector = DataCollector(dedup_cache=str(Path(output_dir) / "pipeline_dedup.json"))
    raw_records = list(collector.collect(source_dir))
    stats["stages"]["collect"] = collector.get_stats()
    print(f"  수집 완료: {len(raw_records)}건")

    print("[2/7] 데이터 정제 중...")
    cleaner = DataCleaner(min_korean_ratio=DEFAULT_CONFIG["min_korean_ratio"])
    cleaned_records = []
    clean_failed = 0
    pii_total = 0
    for record in raw_records:
        result = cleaner.clean(record.content)
        if result.passed:
            record.content = result.text
            record.metadata.update(
                {
                    "pii_count": result.pii_count,
                    "korean_ratio": result.korean_ratio,
                }
            )
            pii_total += result.pii_count
            cleaned_records.append(record)
        else:
            clean_failed += 1
            quarantine.add(record.sha256, record.source_path, result.reject_reason, "unknown")
    stats["stages"]["clean"] = {
        "passed": len(cleaned_records),
        "failed": clean_failed,
        "pii_redactions": pii_total,
    }

    print("[3/7] 품질 검증 중...")
    quality_filter = QualityFilter(
        min_score=DEFAULT_CONFIG["min_quality_score"],
        max_ngram_dup=DEFAULT_CONFIG["max_ngram_dup"],
        restricted_min_score=DEFAULT_CONFIG["restricted_min_quality_score"],
    )
    quality_records = []
    quality_failed = 0
    by_domain: dict[str, int] = {}
    for record in cleaned_records:
        quality = quality_filter.evaluate(record.content)
        if quality.passed:
            record.metadata.update(
                {
                    "quality_score": quality.score,
                    "domain": quality.domain,
                    "hallucination_count": quality.hallucination_count,
                    "ngram_duplication_ratio": quality.ngram_duplication_ratio,
                }
            )
            by_domain[quality.domain] = by_domain.get(quality.domain, 0) + 1
            quality_records.append(record)
        else:
            quality_failed += 1
            quarantine.add(record.sha256, record.source_path, quality.reject_reason, quality.domain)
    stats["stages"]["quality"] = {
        "passed": len(quality_records),
        "failed": quality_failed,
        "by_domain": by_domain,
    }

    print("[4/7] 학습 포맷 변환 중...")
    formatter = DataFormatter()
    training_records: list[dict] = []
    for record in quality_records:
        formatted = formatter.format_document(
            record.content,
            record.metadata.get("domain", "general"),
            float(record.metadata.get("quality_score", 0.0)),
            record.source_path,
        )
        if formatted is not None:
            training_records.append(json.loads(formatter.to_jsonl(formatted)))
    stats["stages"]["format"] = {"total": len(training_records)}

    stats["stages"]["quarantine"] = {"count_preview": quarantine.count()}

    if not training_records:
        raise RuntimeError("PIPELINE_NO_TRAINING_RECORDS: training_records 0건 — 파이프라인 중단")

    if dry_run:
        print("[5/7] dry-run 종료: 분할/저장 생략")
        stats["dry_run_ok"] = True
        stats["elapsed_seconds"] = round(time.time() - start, 3)
        tmp_path = Path("tmp")
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "pipeline_run_dry_result.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("PIPELINE_RUN_OK=1")
        return stats

    print("[5/7] 분할 저장 중...")
    split_result = DataSplitter().split(training_records, output_dir)
    stats["stages"]["split"] = split_result

    print("[6/7] quarantine 저장 중...")
    quarantine.save()
    stats["stages"]["quarantine"] = {"count": quarantine.count()}

    print("[7/7] 매니페스트 저장 중...")
    stats["elapsed_seconds"] = round(time.time() - start, 3)
    manifest = create_manifest(source_dir, output_dir, DEFAULT_CONFIG, stats)
    manifest_path = save_manifest(manifest, output_dir)
    stats["manifest_path"] = str(manifest_path)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pipeline_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("PIPELINE_RUN_OK=1")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_pipeline(args.source_dir, args.output_dir, args.dry_run)


if __name__ == "__main__":
    main()
