from __future__ import annotations

import json
from pathlib import Path

from scripts.convert.convert_manifest_v1 import create_manifest


def test_create_manifest_dry_run(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest = create_manifest("dry_run", "a", "b", "c", "v1", {}, 0.0, {"x": 1})
    assert manifest["run_mode"] == "dry_run"
    assert manifest["adapter_digest"] is None
    assert "tokenizer_file_digests" in manifest
    assert "onnx_export_method" in manifest
    assert "mnn_stdout_digest" in manifest
    assert "ort_runtime_verified" in manifest
    assert (tmp_path / "tmp" / "conversion_manifest.json").exists()


def test_create_manifest_real_run_records_digests(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stage_results = {
        "merge": {"adapter_digest": "a" * 16, "merged_digest": "b" * 16},
        "onnx": {"onnx_digest": "c" * 16, "export_method": "torch.onnx.export:dynamo"},
        "verify_onnx": {
            "exporter_report_digests": {"onnx_export_report.md": "f" * 16},
            "runtime_verified": False,
            "structure_verified": True,
            "external_data_digests": {"model.onnx.data": "1" * 16},
        },
        "mnn": {"mnn_digest": "d" * 16, "stdout_digest": "2" * 16, "stderr_digest": "3" * 16},
        "package": {
            "pkg_digest": "e" * 16,
            "tokenizer_digests": {"tokenizer.json": "4" * 16},
            "config_digests": {"config.json": "5" * 16},
            "generation_config_digest": "6" * 16,
        },
    }
    manifest = create_manifest("real_run", "a", "b", "c", "v1", stage_results, 1.2)
    assert manifest["adapter_digest"] == "a" * 16
    assert manifest["package_digest"] == "e" * 16
    assert manifest["onnx_export_method"] == "torch.onnx.export:dynamo"
    assert manifest["mnn_stdout_digest"] == "2" * 16
    assert manifest["ort_runtime_verified"] is False
