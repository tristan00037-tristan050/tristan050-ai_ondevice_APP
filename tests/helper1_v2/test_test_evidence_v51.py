from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import butler_pc_core.helper1.test_evidence as evidence_module
from butler_pc_core.helper1.test_evidence import (
    TestEvidenceError as EvidenceError,
    build_evidence_index,
    parse_junit,
    run_test_lane,
)


def test_junit_counts_are_runner_derived(tmp_path) -> None:
    report = tmp_path / "result.xml"
    report.write_text(
        '<testsuite tests="4" failures="1" errors="1" skipped="1"><testcase/></testsuite>',
        encoding="utf-8",
    )
    assert parse_junit(report) == (4, 1, 1, 1, 1)


def test_unknown_lane_cannot_supply_arbitrary_argv(tmp_path) -> None:
    with pytest.raises(EvidenceError, match="TEST_LANE_NOT_ALLOWLISTED"):
        run_test_lane("python -c arbitrary", tmp_path)


def test_lane_uses_shell_false_fixed_cwd_and_bounded_environment(tmp_path, monkeypatch) -> None:
    observed = {}

    def fake_run(argv, **kwargs):
        observed.update({"argv": argv, **kwargs})
        report_arg = next(item for item in argv if item.startswith("--junitxml="))
        Path(report_arg.split("=", 1)[1]).write_text(
            '<testsuite tests="243" failures="0" errors="0" skipped="0"/>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, 0, b"ok", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(evidence_module, "_source_identity", lambda: ("1" * 40, "2" * 40))
    monkeypatch.setattr(evidence_module, "_runner_version", lambda *_: ("pytest", "test"))
    result = run_test_lane("python-helper1-v4-original", tmp_path)
    assert result.status == "PASSED"
    assert observed["shell"] is False
    assert observed["stdin"] is subprocess.DEVNULL
    assert "HELPER1_VERDICT_SIGNING_KEY_B64" not in observed["env"]
    assert observed["cwd"].name != "tests"


def test_blocked_lane_has_zero_counts_and_index_stays_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(evidence_module, "_source_identity", lambda: ("1" * 40, "2" * 40))
    blocked = run_test_lane("native-macos-helper1-v51", Path("unused"))
    index = build_evidence_index((blocked,))
    assert index["all_required_lanes_passed"] is False
    assert index["required_lanes_blocked"] == 1


def test_native_macos_lane_is_explicitly_blocked_without_invented_counts(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(evidence_module, "_source_identity", lambda: ("1" * 40, "2" * 40))
    result = run_test_lane("native-macos-helper1-v51", tmp_path)
    assert result.status == "BLOCKED"
    assert result.collected == result.passed == result.failed == result.errors == result.skipped == 0
    assert result.error_code == "MACOS_NATIVE_LANE_NOT_CONFIGURED"
