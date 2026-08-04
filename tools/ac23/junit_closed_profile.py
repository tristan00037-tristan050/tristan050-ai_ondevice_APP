#!/usr/bin/env python3
"""Source-side closed-world parser for the pinned pytest JUnit profile."""

from __future__ import annotations

import json
import math
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone


PROFILE = "pytest-junit-pass-v2"
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
XML_DECLARATION = b'<?xml version="1.0" encoding="utf-8"?>'
JUNIT_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00\Z"
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
    if type(payload) is not bytes or not payload or len(payload) > max_bytes:
        _raise("E_EVIDENCE_JUNIT_SIZE")
    if payload.startswith(b"\xef\xbb\xbf"):
        _raise("E_EVIDENCE_JUNIT_DECLARATION")
    try:
        payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _raise("E_EVIDENCE_JUNIT_DECLARATION")
    if not payload.startswith(XML_DECLARATION):
        _raise("E_EVIDENCE_JUNIT_DECLARATION")
    body = payload[len(XML_DECLARATION) :]
    if not body.startswith(b"<") or body.endswith(tuple(bytes([value]) for value in range(0x21))):
        _raise("E_EVIDENCE_JUNIT_DECLARATION")
    if any(value < 0x20 for value in payload):
        _raise("E_EVIDENCE_JUNIT_DECLARATION")
    folded = payload.upper()
    if (
        b"<?" in body
        or b"<!--" in payload
        or b"<![CDATA[" in folded
        or b"<!DOCTYPE" in folded
        or b"<!ENTITY" in folded
    ):
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
            if type(attribute) is not str or "{" in attribute or "}" in attribute:
                _raise("E_EVIDENCE_JUNIT_STRUCTURE")


def _validate_layout_text(value: str | None) -> None:
    if value is not None and (type(value) is not str or value.strip(" ") != ""):
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


def _validate_text(value: str, *, max_bytes: int) -> None:
    if not value or value != value.strip() or unicodedata.normalize("NFC", value) != value:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    if len(value.encode("utf-8")) > max_bytes or "\x00" in value:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    if any(ord(character) < 0x20 for character in value):
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")


def _validate_timestamp(value: str) -> None:
    if type(value) is not str or JUNIT_TIMESTAMP.fullmatch(value) is None:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _raise("E_EVIDENCE_JUNIT_ATTRIBUTE")
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00") != value:
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
    _validate_layout_text(root.text)
    _validate_layout_text(root.tail)
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
    _validate_layout_text(suite.text)
    _validate_layout_text(suite.tail)
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
        _validate_layout_text(case.text)
        _validate_layout_text(case.tail)
        _require_attributes(
            case,
            CASE_ATTRIBUTES,
            max_attribute_count=max_attribute_count,
            max_attribute_value_bytes=max_attribute_value_bytes,
        )
        classname = case.attrib["classname"]
        name = case.attrib["name"]
        _validate_text(classname, max_bytes=max_testcase_id_bytes)
        _validate_text(name, max_bytes=max_testcase_id_bytes)
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
        parser = ET.XMLParser(
            target=ET.TreeBuilder(insert_comments=True, insert_pis=True)
        )
        root = ET.fromstring(payload, parser=parser)
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
