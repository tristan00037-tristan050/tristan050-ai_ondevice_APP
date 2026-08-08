"""Differential regression: the trusted JUnit parser and the producer parser are
genuinely distinct implementations with different suite limits.

The protected verifier chain (verify-required-test-nodes.mjs) is wired to
scripts/ci/trusted_parse_junit_xml.py (MAX_SUITES = 4096). The producer copy
scripts/ci/parse_junit_xml.py is stricter (MAX_SUITES = 2048) and may be loosened
freely without touching the trusted chain. This test pins the observable
difference at the 2048/2049 boundary so that a future "accidental unification"
(repointing the chain at the producer parser, or collapsing the limits) is caught.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_sidecar_token

ROOT = Path(__file__).resolve().parents[2]
TRUSTED = ROOT / "scripts/ci/trusted_parse_junit_xml.py"
PRODUCER = ROOT / "scripts/ci/parse_junit_xml.py"

PRODUCER_MAX_SUITES = 2048  # scripts/ci/parse_junit_xml.py
TRUSTED_MAX_SUITES = 4096   # scripts/ci/trusted_parse_junit_xml.py


def _junit_with_suites(total_suites: int) -> str:
    """Build a valid JUnit doc whose suite-family element count == total_suites.

    Every <testsuite>/<testsuites> element counts toward the suite total. The root
    <testsuites> is 1; every child suite has a unique identity and one testcase,
    because the protected parser rejects empty or duplicate suites.
    """
    assert total_suites >= 2
    count = total_suites - 1
    inner = "".join(
        f'<testsuite name="s{index}" tests="1" failures="0" errors="0" skipped="0">'
        f'<testcase classname="t.x" name="x{index}"/></testsuite>'
        for index in range(count)
    )
    doc = (
        f'<testsuites tests="{count}" failures="0" errors="0" skipped="0">'
        + inner
        + "</testsuites>"
    )
    return doc


def _run(parser: Path, xml: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(parser), "-"],
        input=xml,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_producer_rejects_2049_suites_but_trusted_accepts() -> None:
    xml = _junit_with_suites(PRODUCER_MAX_SUITES + 1)  # 2049

    trusted = _run(TRUSTED, xml)
    assert trusted.returncode == 0, trusted.stdout + trusted.stderr
    assert '"nodes"' in trusted.stdout

    producer = _run(PRODUCER, xml)
    assert producer.returncode == 1, producer.stdout + producer.stderr
    assert "JUNIT_SUITE_LIMIT_EXCEEDED" in producer.stdout


def test_producer_boundary_accepts_2048_suites() -> None:
    # At exactly the producer limit both parsers accept: proves 2049 is the first
    # divergent point, not an unrelated failure.
    xml = _junit_with_suites(PRODUCER_MAX_SUITES)
    for parser in (PRODUCER, TRUSTED):
        result = _run(parser, xml)
        assert result.returncode == 0, (
            str(parser) + "\n" + result.stdout + result.stderr
        )
        assert '"nodes"' in result.stdout


def test_the_two_parsers_are_not_the_same_file() -> None:
    assert TRUSTED.read_bytes() != PRODUCER.read_bytes()
