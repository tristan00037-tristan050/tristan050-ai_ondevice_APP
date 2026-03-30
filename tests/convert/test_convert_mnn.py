from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.convert import StructureOrInputError
from scripts.convert.convert_mnn_v2 import convert_to_mnn
from scripts.convert.convert_verify_mnn_v2 import verify_mnn


def test_convert_to_mnn_missing_binary_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    onnx_path = tmp_path / "a.onnx"
    onnx_path.write_bytes(b"onnx")
    monkeypatch.setenv("MNNCONVERT_BIN", "")
    monkeypatch.setattr("scripts.convert.convert_mnn_v2.resolve_mnnconvert_binary", lambda: None)
    with pytest.raises(StructureOrInputError):
        convert_to_mnn(str(onnx_path), str(tmp_path / "a.mnn"))


def test_convert_to_mnn_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    onnx_path = tmp_path / "a.onnx"
    onnx_path.write_bytes(b"onnx")
    out_path = tmp_path / "a.mnn"

    def fake_run(cmd, capture_output=True, text=True):
        out_path.write_bytes(b"mnn")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr("scripts.convert.convert_mnn_v2.resolve_mnnconvert_binary", lambda: "/usr/bin/MNNConvert")
    monkeypatch.setattr("scripts.convert.convert_mnn_v2.subprocess.run", fake_run)

    result = convert_to_mnn(str(onnx_path), str(out_path))
    assert result["quant_bits"] == 8
    assert len(result["stdout_digest"]) == 16
    assert len(result["stderr_digest"]) == 16
    assert out_path.exists()


def test_verify_mnn_dryrun():
    result = verify_mnn("", dry_run=True)
    assert result["all_pass"] is True
