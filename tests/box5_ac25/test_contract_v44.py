from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from ac25 import contract_parse


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/verify/verify_repo_contracts.sh"


def _function(source: str, name: str) -> str:
    start = source.index(f"{name}()")
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(name)


def _run_fixture(body: str, *, cleanup_rc: int = 0):
    source = SCRIPT.read_text(encoding="utf-8")
    functions = "\n".join(
        _function(source, name)
        for name in ("record_first_failure", "emit_primary_once", "on_error", "on_exit")
    )
    fixture = f"""set -Euo pipefail
shopt -s inherit_errexit 2>/dev/null || true
CURRENT_GUARD=NONE
FIRST_FAILED_GUARD=NONE
FAILURE_RECORDED=0
PRIMARY_EMITTED=0
{functions}
cleanup_non_primary_diagnostics() {{ return {cleanup_rc}; }}
trap 'on_error' ERR
trap 'EXIT_STATUS=$?; on_exit' EXIT
{body}
"""
    return subprocess.run(["bash", "-c", fixture], text=True, capture_output=True)


def test_success_emits_primary_none_exactly_once():
    result = _run_fixture("true")
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["REPO_CONTRACTS_FAILED_GUARD=NONE"]


def test_failure_emits_first_failed_guard_exactly_once():
    result = _run_fixture("CURRENT_GUARD='first guard'; false")
    assert result.returncode != 0
    assert result.stdout.splitlines() == ["REPO_CONTRACTS_FAILED_GUARD=first guard"]


def test_cleanup_failure_does_not_hide_original_failure():
    result = _run_fixture("CURRENT_GUARD='original guard'; false", cleanup_rc=9)
    assert result.returncode != 0
    assert result.stdout.splitlines() == ["REPO_CONTRACTS_FAILED_GUARD=original guard"]


def test_pipeline_failure_records_first_guard():
    result = _run_fixture("CURRENT_GUARD='pipeline guard'; false | true")
    assert result.returncode != 0
    assert result.stdout.splitlines() == ["REPO_CONTRACTS_FAILED_GUARD=pipeline guard"]


def test_subshell_failure_records_first_guard():
    result = _run_fixture("CURRENT_GUARD='subshell guard'; (false)")
    assert result.returncode != 0
    assert result.stdout.splitlines() == ["REPO_CONTRACTS_FAILED_GUARD=subshell guard"]


def test_unbound_variable_preserves_nonzero_exit():
    result = _run_fixture("CURRENT_GUARD='nounset guard'; echo \"${AC25_MISSING_VALUE}\"")
    assert result.returncode != 0
    assert result.stdout.splitlines() == ["REPO_CONTRACTS_FAILED_GUARD=nounset guard"]


def test_production_shell_has_one_primary_printf():
    source = SCRIPT.read_text(encoding="utf-8")
    calls = re.findall(r"printf\s+'%s\\n'\s+\"REPO_CONTRACTS_FAILED_GUARD=", source)
    assert len(calls) == 1


def test_duplicate_primary_rejected_before_mapping():
    result = contract_parse.parse_contract_observation(
        b"REPO_CONTRACTS_FAILED_GUARD=NONE\nREPO_CONTRACTS_FAILED_GUARD=NONE\n"
    )
    assert result.parse_error_code == contract_parse.CONTRACT_DUPLICATE_PRIMARY


def test_missing_primary_rejected():
    result = contract_parse.parse_contract_observation(b"ONE" + b"_OK=" + b"1\n")
    assert result.parse_error_code == contract_parse.CONTRACT_MISSING_PRIMARY


def test_duplicate_guard_rejected_before_mapping():
    result = contract_parse.parse_contract_observation(
        b"REPO_CONTRACTS_FAILED_GUARD=NONE\n"
        + (b"ONE" + b"_OK=" + b"1\n") * 2
    )
    assert result.parse_error_code == contract_parse.CONTRACT_DUPLICATE_GUARD
    assert len(result.guard_items) == 2


def test_guard_like_unknown_line_rejected():
    result = contract_parse.parse_contract_observation(
        b"REPO_CONTRACTS_FAILED_GUARD=NONE\nbad" + b"_OK=" + b"1\n"
    )
    assert result.parse_error_code == contract_parse.CONTRACT_MALFORMED_GUARD_KEY


def test_allowed_meta_line_not_counted_as_guard():
    result = contract_parse.parse_contract_observation(
        b"== guard: sample ==\nREPO_CONTRACTS_FAILED_GUARD=NONE\nONE"
        + b"_OK=" + b"1\n"
    )
    assert result.parse_error_code == contract_parse.PARSE_OK
    assert result.guard_items == ((0, "ONE_OK", "1"),)
    assert len(result.meta_items) == 1
