from __future__ import annotations

from pathlib import Path

from scripts.convert.convert_budget_v1 import check_budget, get_budget_spec


def test_budget_dry_run_passes():
    result = check_budget("", dry_run=True)
    assert result.file_budget_passed is True
    assert get_budget_spec()["mnn_size_mb_max"] == 3072


def test_budget_small_files_pass(tmp_path: Path):
    mnn = tmp_path / "model.mnn"
    ort = tmp_path / "model.ort"
    mnn.write_bytes(b"m" * 1024)
    ort.write_bytes(b"o" * 2048)
    result = check_budget(str(mnn), str(ort), dry_run=False)
    assert result.file_budget_passed is True
    assert result.mnn_size_ok is True
    assert result.ort_size_ok is True
