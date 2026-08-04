#!/usr/bin/env python3
"""Source-side closed-world parser for the pinned pytest JUnit profile."""

from __future__ import annotations

import json
import math
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime


PROFILE = "pytest-junit-pass-v1"
ROOT_ATTRIBUTES = {"name"}
SUITE_ATTRIBUTES = {
    "name",
    "errors",
    "failures",
    "skipped",
    "tests",
    "time",
    "timestamp",
    "hostname",
}
CASE_ATTRIBUTES = {"classname", "name", "time"}
KNOWN_TAGS = {"testsuites", "testsuite", "testcase"}
STATUS_TAGS = {"failure", "error", "skipped"}
CANONICAL_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
CANONICAL_DURATION = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
XML_DECLARATION = re.compile(
    br"<\?xml[ \t]+version=(?:\"1\.0\"|'1\.0')[ \t]+"
    br"encoding=(?:\"utf-8\"|'utf-8')[ \t]*\?>",
    re.IGNORECASE,
)


class JunitProfileError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CanonicalJunitResult:
    profile: str
    tests: int
    failures: int
    errors: int
    skipped: int
    testcase_ids: tuple[str, ...]

    def to_bytes(self) -> bytes:
        return (
            json.dumps(
                {
                    "profile": self.profile,
                    "tests": self.tests,
                    "failures": self.failures,
                    "errors": self.errors,
                    "skipped": self.skipped,
                    "testcase_ids": list(self.testcase_ids),
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")


def _raise(code: str) -> None:
    raise JunitProfileError(code)


def preflight_xml_bytes(payload: bytes, *, max_bytes: int) -> None:
    if not isinstance(payload, bytes) or not payload or len(payload) > max_bytes:
        _raise("E_EVIDENCE_JUNIT_SIZE")
    if b"\x00" in payload:
        _raise("E_EVIDENCE_JUNIT_DECLARATION")
    folded = payload.upper()
    if b"<!DOCTYPE" in folded or b"<!ENTITY" in folded:
        _raise("E_EVIDENCE_JUNIT_DECLARATION")
    candidate = payload[3:] if payload.startswith(b"\xef\xbb\xbf") else payload
    if candidate.startswith(b"<?xml"):
        declaration_end = candidate.find(b"?>")
        if declaration_end < 0 or XML_DECLARATION.fullmatch(
            candidate[: declaration_end + 2]
        ) is None:
            _raise("E_EVIDENCE_JUNIT_DECLARATION")
    elif not candidate.startswith(b"<"):
        _raise("E_EVIDENCE_JUNIT_DECLARATION")


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def scan_all_xml_elements(root: ET.Element, *, max_elements: int) -> None:
    seen: set[int] = set()
    elements: list[ET.Element] = []
    for count, element in enumerate(root.iter(), start=1):
        if count > max_elements:
            _raise("E_EVIDENCE_JUNIT_SIZE")
        marker = id(element)
        if marker in seen:
            _raise("E_EVIDENCE_JUNIT_STRUCTURE")
        seen.add(marker)
        elements.append(element)
    for element in elements:
        local = _local_name(element.tag)
        if local in STATUS_TAGS:
            _raise("E_EVIDENCE_JUNIT_STATUS")
    for element in elements:
        if (
            not isinstance(element.tag, str)
            or element.tag not in KNOWN_TAGS
            or "{" in element.tag
            or "}" in element.tag
        ):
            _raise("E_EVIDENCE_JUNIT_STRUCTURE")
        for attribute in element.attrib:
            if "{" in attribute or "}" in attribute:
                _raise("E_EVIDENCE_JUNIT_STRUCTURE")


def _require_attributes(
    element: ET.Element,
    expected: set[str],
    *,
    max_attribute_count: int,
    max_attribute_value_bytes: int,
) -> None:
    if len(element.attrib) > max_attribute_count or set(element.attrib) != expected:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    for value in element.attrib.values():
        if not isinstance(value, str) or len(value.encode("utf-8")) > max_attribute_value_bytes:
            _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")


def parse_canonical_decimal(value: str) -> int:
    if CANONICAL_DECIMAL.fullmatch(value) is None:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    return int(value)


def _validate_duration(value: str) -> None:
    if CANONICAL_DURATION.fullmatch(value) is None:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")


def _validate_text(value: str, *, max_bytes: int, allow_xml_newline_reference: bool = False) -> None:
    if not value or value != value.strip() or unicodedata.normalize("NFC", value) != value:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    if len(value.encode("utf-8")) > max_bytes or "\x00" in value:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    # Existing pinned pytest parameter IDs contain XML character references for
    # newlines.  ElementTree decodes those references, so reject literal control
    # characters other than that producer-specific representation.
    if any(ord(character) < 0x20 and character not in ({"\n"} if allow_xml_newline_reference else set()) for character in value):
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")


def validate_pytest_junit_grammar(
    root: ET.Element,
    *,
    max_attribute_count: int,
    max_attribute_value_bytes: int,
    max_testcase_id_bytes: int,
    max_testcases_per_run: int,
) -> tuple[str, ...]:
    if root.tag != "testsuites":
        _raise("E_EVIDENCE_JUNIT_STRUCTURE")
    _require_attributes(
        root,
        ROOT_ATTRIBUTES,
        max_attribute_count=max_attribute_count,
        max_attribute_value_bytes=max_attribute_value_bytes,
    )
    if root.attrib["name"] != "pytest tests":
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    suites = list(root)
    if len(suites) != 1 or suites[0].tag != "testsuite":
        _raise("E_EVIDENCE_JUNIT_STRUCTURE")
    suite = suites[0]
    _require_attributes(
        suite,
        SUITE_ATTRIBUTES,
        max_attribute_count=max_attribute_count,
        max_attribute_value_bytes=max_attribute_value_bytes,
    )
    if suite.attrib["name"] != "pytest":
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    _validate_duration(suite.attrib["time"])
    _validate_timestamp(suite.attrib["timestamp"])
    _validate_text(suite.attrib["hostname"], max_bytes=max_attribute_value_bytes)

    cases = list(suite)
    if not cases or len(cases) > max_testcases_per_run:
        _raise("E_EVIDENCE_JUNIT_COUNT")
    pairs: set[tuple[str, str]] = set()
    display_ids: set[str] = set()
    for case in cases:
        if case.tag != "testcase" or list(case):
            _raise("E_EVIDENCE_JUNIT_STRUCTURE")
        _require_attributes(
            case,
            CASE_ATTRIBUTES,
            max_attribute_count=max_attribute_count,
            max_attribute_value_bytes=max_attribute_value_bytes,
        )
        classname = case.attrib["classname"]
        name = case.attrib["name"]
        _validate_text(classname, max_bytes=max_testcase_id_bytes)
        _validate_text(
            name,
            max_bytes=max_testcase_id_bytes,
            allow_xml_newline_reference=True,
        )
        _validate_duration(case.attrib["time"])
        pair = (classname, name)
        display_id = f"{classname}::{name}"
        if pair in pairs or display_id in display_ids:
            _raise("E_EVIDENCE_JUNIT_IDENTITY")
        pairs.add(pair)
        display_ids.add(display_id)

    declared = {
        key: parse_canonical_decimal(suite.attrib[key])
        for key in ("tests", "failures", "errors", "skipped")
    }
    if any(declared[key] != 0 for key in ("failures", "errors", "skipped")):
        _raise("E_EVIDENCE_JUNIT_STATUS")
    if declared["tests"] != len(cases):
        _raise("E_EVIDENCE_JUNIT_COUNT")
    return tuple(sorted(display_ids))


def parse_pytest_junit_closed(
    payload: bytes,
    *,
    expected_testcase_ids: frozenset[str],
    max_bytes: int,
    max_elements: int,
    max_testcases_per_run: int = 100_000,
    max_attribute_count_per_element: int = 8,
    max_attribute_value_bytes: int = 8192,
    max_testcase_id_bytes: int = 4096,
) -> CanonicalJunitResult:
    preflight_xml_bytes(payload, max_bytes=max_bytes)
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, ValueError):
        _raise("E_EVIDENCE_JUNIT_PARSE")
    scan_all_xml_elements(root, max_elements=max_elements)
    testcase_ids = validate_pytest_junit_grammar(
        root,
        max_attribute_count=max_attribute_count_per_element,
        max_attribute_value_bytes=max_attribute_value_bytes,
        max_testcase_id_bytes=max_testcase_id_bytes,
        max_testcases_per_run=max_testcases_per_run,
    )
    if frozenset(testcase_ids) != expected_testcase_ids:
        _raise("E_EVIDENCE_TESTCASE_SET")
    return CanonicalJunitResult(
        profile=PROFILE,
        tests=len(testcase_ids),
        failures=0,
        errors=0,
        skipped=0,
        testcase_ids=testcase_ids,
    )
