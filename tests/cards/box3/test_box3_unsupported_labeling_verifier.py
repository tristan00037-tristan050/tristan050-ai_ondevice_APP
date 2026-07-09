from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_verifier():
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts/verify_box3_unsupported_claim_labeling.py"
    spec = importlib.util.spec_from_file_location("verify_box3_unsupported_claim_labeling", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verifier_skips_missing_changed_path_without_read_error():
    verifier = _load_verifier()
    assert verifier._read_changed_text("__missing__/한글 삭제 경로.txt") is None


def test_verifier_result_keys_are_boolean_only(capsys):
    verifier = _load_verifier()
    assert verifier.main() in {0, 1}
    output = capsys.readouterr().out.splitlines()
    result_lines = [line for line in output if line.startswith("BOX3_UNSUPPORTED_LABELING_")]
    assert result_lines
    for line in result_lines:
        value = line.rsplit("=", 1)[-1]
        assert value in {"0", "1"}
