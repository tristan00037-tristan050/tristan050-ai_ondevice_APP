from __future__ import annotations

import hashlib

import pytest

from scripts.ci.verify_box5_junit_evidence import verify
from scripts.ci.trusted_parse_junit_xml import parse_bytes


def _document(*suites: str, tests: int, failures: int = 0) -> bytes:
    return (
        f'<testsuites tests="{tests}" failures="{failures}" errors="0" skipped="0">'
        + "".join(suites)
        + "</testsuites>"
    ).encode()


def _suite(name: str, *cases: str, tests: int, failures: int = 0) -> str:
    return (
        f'<testsuite name="{name}" tests="{tests}" failures="{failures}" errors="0" skipped="0">'
        + "".join(cases)
        + "</testsuite>"
    )


PASS = '<testcase classname="box5.authorization" name="allow"/>'
FAIL = '<testcase classname="box5.authorization" name="deny"><failure/></testcase>'


def test_trusted_parser_accepts_semantically_consistent_raw_junit() -> None:
    nodes = parse_bytes(_document(_suite("box5", PASS, tests=1), tests=1))
    assert nodes == [
        {
            "runner": "pytest",
            "file": "box5/authorization.py",
            "title": "allow",
            "status": "passed",
        }
    ]


@pytest.mark.parametrize(
    "raw,code",
    [
        (
            _document(_suite("box5", FAIL, tests=1, failures=0), tests=1),
            "JUNIT_SUITE_COUNT_MISMATCH",
        ),
        (
            _document(
                _suite("same", PASS, tests=1),
                _suite("same", '<testcase classname="x" name="b"/>', tests=1),
                tests=2,
            ),
            "JUNIT_DUPLICATE_OR_EMPTY_SUITE_IDENTITY",
        ),
        (
            _document(_suite("box5", PASS, PASS, tests=2), tests=2),
            "JUNIT_DUPLICATE_TESTCASE",
        ),
        (
            b'<!DOCTYPE x [<!ENTITY leak SYSTEM "file:///etc/passwd">]>'
            b'<testsuite name="x" tests="0" failures="0" errors="0" skipped="0"/>',
            "JUNIT_DTD_OR_ENTITY_FORBIDDEN",
        ),
    ],
)
def test_trusted_parser_blocks_semantic_forgery(raw: bytes, code: str) -> None:
    with pytest.raises(ValueError, match=code):
        parse_bytes(raw)


def _large_pytest_document(count: int) -> bytes:
    cases = "".join(
        f'<testcase classname="box5.authorization" name="case_{index}"/>'
        for index in range(count)
    )
    return _document(_suite("pytest", cases, tests=count), tests=count)


def test_box5_evidence_verifier_requires_raw_digest_and_protected_minimum(tmp_path) -> None:
    raw = _large_pytest_document(382)
    path = tmp_path / "target.xml"
    path.write_bytes(raw)
    result = verify(path, hashlib.sha256(raw).hexdigest())
    assert result["tests"] == 382
    with pytest.raises(ValueError, match="JUNIT_DIGEST_MISMATCH"):
        verify(path, "0" * 64)


def test_box5_evidence_verifier_blocks_test_count_regression(tmp_path) -> None:
    raw = _large_pytest_document(381)
    path = tmp_path / "target.xml"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="JUNIT_TEST_COUNT_BELOW_POLICY"):
        verify(path, hashlib.sha256(raw).hexdigest())
