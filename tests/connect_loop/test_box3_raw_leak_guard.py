import importlib.util
import json
from pathlib import Path

import pytest

from butler_pc_core.cards.box3.security import (
    Box3SecurityError,
    assert_no_raw_persistence,
    assert_runtime_text_safe,
    scan_forbidden_text,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("alice@example.com", "PII_EMAIL"),
        ("900101-1234567", "PII_KOREAN_RRN"),
        ("sk-proj-a1b2c3d4e5f6g7h8", "SECRET"),
        ("Bearer abcdefghijklmnop", "SECRET"),
        ("/Users/person/Desktop/raw.docx", "LOCAL_PATH"),
        ("C:/Users/person/raw.pdf", "LOCAL_PATH"),
    ],
)
def test_forbidden_runtime_text_patterns(text, expected):
    assert expected in scan_forbidden_text(text)
    with pytest.raises(Box3SecurityError):
        assert_runtime_text_safe(text)


def test_forbidden_persistence_keys_are_blocked():
    with pytest.raises(Box3SecurityError) as exc:
        assert_no_raw_persistence({"filename": "contract.docx"})
    assert "BLOCK_RAW_KEY" in str(exc.value)


def test_evidence_directory_contains_no_forbidden_scalars():
    evidence_dir = Path(__file__).resolve().parents[2] / "evidence" / "box3"
    if not evidence_dir.exists():
        return
    for path in evidence_dir.rglob("*"):
        if path.is_file() and path.suffix == ".json":
            assert_no_raw_persistence(json.loads(path.read_text(encoding="utf-8")))
        if path.is_file() and path.suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                assert_no_raw_persistence(json.loads(line))
        if path.is_file() and path.suffix in {".md", ".txt"}:
            findings = scan_forbidden_text(path.read_text(encoding="utf-8"))
            assert findings == [], f"{path} contains forbidden evidence text: {findings}"


def test_self_check_sanitizes_local_interpreter_paths():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_box3_self_check.py"
    spec = importlib.util.spec_from_file_location("run_box3_self_check", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    output = (
        "platform darwin -- Python 3.9.6 -- "
        "/Library/Developer/CommandLineTools/usr/bin/python3\n"
        "rootdir: /Users/person/Desktop/butler\n"
    )
    sanitized = module.sanitize_test_log(output)

    assert "/Library/" not in sanitized
    assert "/Users/" not in sanitized
    assert "[LOCAL_PATH_REDACTED]" in sanitized
