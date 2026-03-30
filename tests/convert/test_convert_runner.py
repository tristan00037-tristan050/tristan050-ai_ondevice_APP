from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.convert.convert_runner_v2 import run_pipeline


def test_run_pipeline_dryrun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    code = run_pipeline("dummy", "work", "pkg", "test-version", dry_run=True)
    assert code == 0
    manifest = json.loads((tmp_path / "tmp" / "conversion_manifest.json").read_text())
    assert manifest["run_mode"] == "dry_run"
    assert "budget_spec" in manifest


def test_run_pipeline_real_run_with_monkeypatched_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        "scripts.convert.convert_merge_v1.merge",
        lambda adapter_dir, output_dir: {
            "base_model_id": "Qwen/Qwen3-4B",
            "adapter_digest": "a" * 16,
            "merged_digest": "b" * 16,
        },
    )
    monkeypatch.setattr(
        "scripts.convert.convert_onnx_v2.convert_to_onnx",
        lambda model_dir, output_path: {
            "opset": 17,
            "onnx_digest": "c" * 16,
            "external_data_used": False,
            "export_method": "torch.onnx.export:dynamo",
        },
    )
    monkeypatch.setattr(
        "scripts.convert.convert_verify_onnx_v2.verify_onnx",
        lambda onnx_path: {
            "all_pass": True,
            "runtime_verified": True,
            "structure_verified": True,
            "exporter_report_digests": {},
            "external_data_digests": {},
        },
    )
    monkeypatch.setattr(
        "scripts.convert.convert_ort_mobile_v1.convert_to_ort",
        lambda onnx_path, output_path: {
            "skipped": False,
            "ort_path": output_path,
            "ort_digest": "f" * 16,
            "size_mb": 10.0,
        },
    )
    monkeypatch.setattr(
        "scripts.convert.convert_mnn_v2.convert_to_mnn",
        lambda onnx_path, output_path: {
            "mnn_digest": "d" * 16,
            "quant_bits": 8,
            "stdout_digest": "1" * 16,
            "stderr_digest": "2" * 16,
        },
    )
    monkeypatch.setattr(
        "scripts.convert.convert_verify_mnn_v2.verify_mnn",
        lambda mnn_path: {"all_pass": True},
    )
    monkeypatch.setattr(
        "scripts.convert.convert_package_v2.create_package",
        lambda *args, **kwargs: {
            "pkg_digest": "e" * 16,
            "tokenizer_digests": {"tokenizer.json": "3" * 16},
            "config_digests": {"config.json": "4" * 16},
            "generation_config_digest": None,
        },
    )

    class FakeBudget:
        file_budget_passed = True
        def __init__(self):
            self.mnn_size_mb = 100.0
            self.mnn_size_ok = True
            self.mnn_target_ok = True
            self.ort_size_mb = 10.0
            self.ort_size_ok = True
            self.fail_reasons = []
            self.first_token_sec = None
            self.throughput_tps = None
            self.load_time_sec = None

    monkeypatch.setattr("scripts.convert.convert_budget_v1.check_budget", lambda *args, **kwargs: FakeBudget())
    monkeypatch.setattr("scripts.convert.convert_budget_v1.get_budget_spec", lambda: {"mnn_size_mb_max": 3072})

    code = run_pipeline("adapter", "work", "pkg", "version-1", dry_run=False)
    assert code == 0
    manifest = json.loads((tmp_path / "tmp" / "conversion_manifest.json").read_text())
    assert manifest["run_mode"] == "real_run"
    assert manifest["package_digest"] == "e" * 16
    assert manifest["onnx_export_method"] == "torch.onnx.export:dynamo"
    assert manifest["mnn_stdout_digest"] == "1" * 16
