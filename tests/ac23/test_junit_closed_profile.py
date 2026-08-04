from __future__ import annotations

import copy
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

import pytest


TOOLS_ROOT = Path(__file__).parents[2] / "tools" / "ac23"
sys.path.insert(0, os.fspath(TOOLS_ROOT))

from junit_closed_profile import (  # noqa: E402
    JunitProfileError as SourceJunitError,
    parse_pytest_junit_closed as parse_source,
)
from verify_candidate_artifact_identity import (  # noqa: E402
    VerificationError as PackagedJunitError,
    parse_pytest_junit_closed as parse_packaged,
)


EXPECTED_ID = "tests.ac23.test_junit_closed_profile::test_fixture_pass"
EXPECTED = frozenset({EXPECTED_ID})
LIMITS = {
    "max_bytes": 16_777_216,
    "max_elements": 200_000,
    "max_testcases_per_run": 100_000,
    "max_attribute_count_per_element": 8,
    "max_attribute_value_bytes": 8192,
    "max_testcase_id_bytes": 4096,
}


def _normal_root() -> ET.Element:
    root = ET.Element("testsuites", {"name": "pytest tests"})
    suite = ET.SubElement(
        root,
        "testsuite",
        {
            "name": "pytest",
            "errors": "0",
            "failures": "0",
            "skipped": "0",
            "tests": "1",
            "time": "0.001",
            "timestamp": "2026-08-04T00:00:00.000000+00:00",
            "hostname": "fixture-host",
        },
    )
    ET.SubElement(
        suite,
        "testcase",
        {
            "classname": "tests.ac23.test_junit_closed_profile",
            "name": "test_fixture_pass",
            "time": "0.001",
        },
    )
    return root


def _xml(root: ET.Element) -> bytes:
    return (
        b'<?xml version="1.0" encoding="utf-8"?>'
        + ET.tostring(root, encoding="utf-8", xml_declaration=False)
    )


def _case() -> ET.Element:
    return next(_normal_root().iter("testcase"))


def _nested_status(tag: str) -> bytes:
    root = _normal_root()
    wrapper = ET.SubElement(next(root.iter("testcase")), "wrapper")
    ET.SubElement(wrapper, tag)
    return _xml(root)


def _nested_root() -> bytes:
    root = _normal_root()
    suite = next(root.iter("testsuite"))
    for child in list(suite):
        suite.remove(child)
    suite.set("tests", "0")
    nested = ET.SubElement(suite, "testsuites", {"name": "pytest tests"})
    nested.append(_case())
    return _xml(root)


def _nested_suite() -> bytes:
    root = _normal_root()
    suite = next(root.iter("testsuite"))
    nested = ET.SubElement(suite, "testsuite", dict(suite.attrib))
    nested.set("tests", "0")
    return _xml(root)


def _unknown_wrapper() -> bytes:
    root = _normal_root()
    ET.SubElement(next(root.iter("testcase")), "wrapper")
    return _xml(root)


def _suite_attr(name: str, value: str | None) -> bytes:
    root = _normal_root()
    suite = next(root.iter("testsuite"))
    if value is None:
        suite.attrib.pop(name)
    else:
        suite.set(name, value)
    return _xml(root)


def _duplicate_pair() -> bytes:
    root = _normal_root()
    suite = next(root.iter("testsuite"))
    suite.append(copy.deepcopy(next(root.iter("testcase"))))
    suite.set("tests", "2")
    return _xml(root)


def _display_collision() -> bytes:
    root = _normal_root()
    suite = next(root.iter("testsuite"))
    first = next(root.iter("testcase"))
    first.set("classname", "a::b")
    first.set("name", "c")
    second = copy.deepcopy(first)
    second.set("classname", "a")
    second.set("name", "b::c")
    suite.append(second)
    suite.set("tests", "2")
    return _xml(root)


def _namespaced_root() -> bytes:
    root = _normal_root()
    root.tag = "{urn:forbidden}testsuites"
    return _xml(root)


def _namespaced_case() -> bytes:
    root = _normal_root()
    next(root.iter("testcase")).tag = "{urn:forbidden}testcase"
    return _xml(root)


def _namespaced_failure() -> bytes:
    root = _normal_root()
    ET.SubElement(next(root.iter("testcase")), "{urn:forbidden}failure")
    return _xml(root)


def _suite_child(tag: str) -> bytes:
    root = _normal_root()
    ET.SubElement(next(root.iter("testsuite")), tag)
    return _xml(root)


def _case_child(tag: str) -> bytes:
    root = _normal_root()
    ET.SubElement(next(root.iter("testcase")), tag)
    return _xml(root)


def _wrapped_case() -> bytes:
    root = _normal_root()
    suite = next(root.iter("testsuite"))
    testcase = next(root.iter("testcase"))
    suite.remove(testcase)
    wrapper = ET.SubElement(suite, "wrapper")
    wrapper.append(testcase)
    return _xml(root)


def _insert_before_root(fragment: bytes) -> bytes:
    payload = _xml(_normal_root())
    declaration = b'<?xml version="1.0" encoding="utf-8"?>'
    return declaration + fragment + payload[len(declaration) :]


def _insert_inside_root(fragment: bytes) -> bytes:
    payload = _xml(_normal_root())
    marker = b"><testsuite "
    assert marker in payload
    return payload.replace(marker, b">" + fragment + b"<testsuite ", 1)


def _insert_after_root(fragment: bytes) -> bytes:
    return _xml(_normal_root()) + fragment


def _element_text(element: str, text: str) -> bytes:
    root = _normal_root()
    target = next(root.iter(element))
    target.text = text
    return _xml(root)


def _testcase_tail(text: str) -> bytes:
    root = _normal_root()
    next(root.iter("testcase")).tail = text
    return _xml(root)


def _timestamp(value: str) -> bytes:
    return _suite_attr("timestamp", value)


def _attribute_reference(attribute: str, reference: bytes) -> bytes:
    payload = _xml(_normal_root())
    marker = (
        b'classname="tests.ac23.test_junit_closed_profile"'
        if attribute == "classname"
        else b'name="test_fixture_pass"'
    )
    replacement = attribute.encode("ascii") + b'="test' + reference + b'fixture"'
    assert marker in payload
    return payload.replace(marker, replacement, 1)


JUNIT_CASES: list[tuple[str, int, bytes, str]] = [
    ("descendant_failure", 1, _nested_status("failure"), "E_EVIDENCE_JUNIT_STATUS"),
    ("descendant_error", 1, _nested_status("error"), "E_EVIDENCE_JUNIT_STATUS"),
    ("descendant_skipped", 1, _nested_status("skipped"), "E_EVIDENCE_JUNIT_STATUS"),
    ("size_limit", 2, b"x" * 257, "E_EVIDENCE_JUNIT_SIZE"),
    ("doctype", 3, b'<!DOCTYPE x><testsuites name="pytest tests"/>', "E_EVIDENCE_JUNIT_DECLARATION"),
    ("entity", 3, b'<!ENTITY x "y"><testsuites name="pytest tests"/>', "E_EVIDENCE_JUNIT_DECLARATION"),
    ("nested_testsuites", 4, _nested_root(), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("nested_testsuite", 4, _nested_suite(), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("unknown_wrapper", 4, _unknown_wrapper(), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("negative_tests", 5, _suite_attr("tests", "-1"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("float_failures", 5, _suite_attr("failures", "1.0"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("signed_errors", 5, _suite_attr("errors", "+0"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("missing_skipped", 5, _suite_attr("skipped", None), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("tests_mismatch", 6, _suite_attr("tests", "2"), "E_EVIDENCE_JUNIT_COUNT"),
    ("hidden_failure_count_zero", 6, _nested_status("failure"), "E_EVIDENCE_JUNIT_STATUS"),
    ("duplicate_pair", 7, _duplicate_pair(), "E_EVIDENCE_JUNIT_IDENTITY"),
    ("display_id_collision", 7, _display_collision(), "E_EVIDENCE_JUNIT_IDENTITY"),
    ("namespaced_root", 8, _namespaced_root(), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("namespaced_testcase", 8, _namespaced_case(), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("namespaced_failure", 8, _namespaced_failure(), "E_EVIDENCE_JUNIT_STATUS"),
    ("failure_under_suite", 9, _suite_child("failure"), "E_EVIDENCE_JUNIT_STATUS"),
    ("passed_under_testcase", 9, _case_child("passed"), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("testcase_under_wrapper", 9, _wrapped_case(), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("comment_before_root", 10, _insert_before_root(b"<!--x-->"), "E_EVIDENCE_JUNIT_DECLARATION"),
    ("comment_inside_root", 10, _insert_inside_root(b"<!--x-->"), "E_EVIDENCE_JUNIT_DECLARATION"),
    ("comment_after_root", 10, _insert_after_root(b"<!--x-->"), "E_EVIDENCE_JUNIT_DECLARATION"),
    ("pi_before_root", 11, _insert_before_root(b"<?x y?>"), "E_EVIDENCE_JUNIT_DECLARATION"),
    ("pi_inside_root", 11, _insert_inside_root(b"<?x y?>"), "E_EVIDENCE_JUNIT_DECLARATION"),
    ("pi_after_root", 11, _insert_after_root(b"<?x y?>"), "E_EVIDENCE_JUNIT_DECLARATION"),
    ("cdata", 12, _insert_inside_root(b"<![CDATA[x]]>"), "E_EVIDENCE_JUNIT_DECLARATION"),
    ("root_text", 13, _element_text("testsuites", "forbidden"), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("suite_text", 13, _element_text("testsuite", "forbidden"), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("testcase_text", 13, _element_text("testcase", "forbidden"), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("testcase_tail", 13, _testcase_tail("forbidden"), "E_EVIDENCE_JUNIT_STRUCTURE"),
    ("iso_week_timestamp", 14, _timestamp("2026-W32-2T00:00:00.000000+00:00"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("basic_timestamp", 14, _timestamp("20260804T000000.000000+00:00"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("timestamp_without_timezone", 14, _timestamp("2026-08-04T00:00:00.000000"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("timestamp_non_utc", 14, _timestamp("2026-08-04T09:00:00.000000+09:00"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("timestamp_wrong_precision", 14, _timestamp("2026-08-04T00:00:00.000+00:00"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("classname_lf_reference", 15, _attribute_reference("classname", b"&#10;"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("name_cr_reference", 15, _attribute_reference("name", b"&#13;"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("name_tab_reference", 15, _attribute_reference("name", b"&#9;"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("bom", 16, b"\xef\xbb\xbf" + _xml(_normal_root()), "E_EVIDENCE_JUNIT_DECLARATION"),
    ("unknown_attribute", 16, _suite_attr("forbidden", "x"), "E_EVIDENCE_JUNIT_ATTRIBUTE"),
    ("noncanonical_declaration", 16, _xml(_normal_root()).replace(b'encoding="utf-8"', b"encoding='utf-8'", 1), "E_EVIDENCE_JUNIT_DECLARATION"),
]


def _parse_source(payload: bytes, expected: frozenset[str] = EXPECTED):
    limits = dict(LIMITS)
    if payload == b"x" * 257:
        limits["max_bytes"] = 256
    return parse_source(payload, expected_testcase_ids=expected, **limits)


def _parse_packaged(payload: bytes, expected: frozenset[str] = EXPECTED):
    limits = dict(LIMITS)
    if payload == b"x" * 257:
        limits["max_bytes"] = 256
    return parse_packaged(payload, expected_testcase_ids=expected, **limits)


def test_closed_junit_normal_canonical_bytes() -> None:
    expected = (
        b'{"errors":0,"failures":0,"profile":"pytest-junit-pass-v2",'
        b'"skipped":0,"testcase_ids":["tests.ac23.test_junit_closed_profile::'
        b'test_fixture_pass"],"tests":1}\n'
    )
    assert _parse_source(_xml(_normal_root())).to_bytes() == expected
    assert _parse_packaged(_xml(_normal_root())).to_bytes() == expected


@pytest.mark.parametrize(
    ("case", "category", "payload", "expected_error"),
    JUNIT_CASES,
    ids=[case for case, _, _, _ in JUNIT_CASES],
)
def test_closed_junit_attack(
    case: str, category: int, payload: bytes, expected_error: str
) -> None:
    del case, category
    for parser, error_type in (
        (_parse_source, SourceJunitError),
        (_parse_packaged, PackagedJunitError),
    ):
        with pytest.raises(error_type) as captured:
            parser(payload)
        assert captured.value.code == expected_error
