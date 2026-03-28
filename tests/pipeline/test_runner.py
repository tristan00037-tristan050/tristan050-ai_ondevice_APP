import json
from pathlib import Path

from scripts.pipeline.pipeline_runner_v2 import run_pipeline


def test_run_pipeline_dry_run(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.txt").write_text(
        "대한민국 헌법 제1조는 대한민국은 민주공화국이다라고 명시하고 있습니다.\n"
        "모든 권력은 국민으로부터 나옵니다.\n"
        "법률은 평등하게 적용되어야 합니다.",
        encoding="utf-8",
    )
    output = tmp_path / "output"
    stats = run_pipeline(str(source), str(output), dry_run=True)
    assert stats["dry_run_ok"] is True
    assert stats["stages"]["collect"]["total_files"] == 1
    assert Path("tmp/pipeline_run_dry_result.json").exists()


def test_run_pipeline_real_run_creates_manifest_and_stats(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.txt").write_text(
        "대한민국 헌법 제1조는 대한민국은 민주공화국이다라고 명시하고 있습니다.\n"
        "모든 권력은 국민으로부터 나옵니다.\n"
        "법률은 평등하게 적용되어야 합니다.\n"
        "국민의 기본권은 보장되어야 합니다.",
        encoding="utf-8",
    )
    output = tmp_path / "output"
    stats = run_pipeline(str(source), str(output), dry_run=False)
    assert (output / "pipeline_stats.json").exists()
    assert (output / "pipeline_manifest.json").exists()
    assert (output / "train.jsonl").exists()
    assert stats["stages"]["split"]["leakage_count"] == 0
