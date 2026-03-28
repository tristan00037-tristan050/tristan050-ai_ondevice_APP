import json

from scripts.pipeline.splitter_v2 import DataSplitter


def test_splitter_writes_expected_split_files(tmp_path):
    records = [
        {
            "domain": "general" if i < 8 else "legal",
            "output_digest_sha256": f"hash{i}",
            "prompt": f"q{i}",
            "completion": f"a{i}",
            "quality_score": 0.8,
            "source": "s",
        }
        for i in range(12)
    ]
    result = DataSplitter(seed=7).split(records, str(tmp_path))
    assert result["leakage_count"] == 0
    for name in ("train", "validation", "test"):
        assert (tmp_path / f"{name}.jsonl").exists()


def test_splitter_keeps_duplicate_digest_in_same_split(tmp_path):
    records = [
        {
            "domain": "legal",
            "output_digest_sha256": "same-digest",
            "prompt": f"q{i}",
            "completion": f"a{i}",
            "quality_score": 0.9,
            "source": "s",
        }
        for i in range(5)
    ] + [
        {
            "domain": "legal",
            "output_digest_sha256": f"hash{i}",
            "prompt": f"q{i}",
            "completion": f"a{i}",
            "quality_score": 0.9,
            "source": "s",
        }
        for i in range(5, 12)
    ]
    result = DataSplitter(seed=3).split(records, str(tmp_path))
    assert result["leakage_count"] == 0
