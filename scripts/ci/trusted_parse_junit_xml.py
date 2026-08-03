from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.parsers import expat


MAX_BYTES = 32 * 1024 * 1024
MAX_SUITES = 4_096
MAX_CASES = 1_000_000
MAX_ATTRIBUTES = 64
MAX_ATTRIBUTE_CHARS = 16_384


def parse_bytes(raw: bytes) -> list[dict[str, str]]:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("JUNIT_SIZE_INVALID")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("JUNIT_BOM_FORBIDDEN")
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("JUNIT_DTD_OR_ENTITY_FORBIDDEN")

    parser = expat.ParserCreate("utf-8")
    parser.buffer_text = True
    suites = 0
    cases = 0
    current: dict[str, str] | None = None
    nodes: list[dict[str, str]] = []
    declared: dict[str, int] | None = None
    suite_names: set[str] = set()
    case_identities: set[tuple[str, str, str]] = set()
    active_suite: dict[str, object] | None = None

    def reject(*_args: object) -> None:
        raise ValueError("JUNIT_DTD_OR_ENTITY_FORBIDDEN")

    def integer(attributes: dict[str, str], name: str) -> int:
        raw_value = attributes.get(name, "0")
        if not raw_value.isascii() or not raw_value.isdecimal():
            raise ValueError("JUNIT_COUNT_INVALID")
        value = int(raw_value)
        if value < 0 or value > MAX_CASES:
            raise ValueError("JUNIT_COUNT_INVALID")
        return value

    def start(name: str, attributes: dict[str, str]) -> None:
        nonlocal suites, cases, current, declared, active_suite
        if (
            len(attributes) > MAX_ATTRIBUTES
            or sum(len(key) + len(value) for key, value in attributes.items())
            > MAX_ATTRIBUTE_CHARS
        ):
            raise ValueError("JUNIT_ATTRIBUTE_LIMIT_EXCEEDED")
        if name in {"testsuite", "testsuites"}:
            suites += 1
            if suites > MAX_SUITES:
                raise ValueError("JUNIT_SUITE_LIMIT_EXCEEDED")
            if declared is None and "tests" in attributes:
                declared = {
                    key: integer(attributes, key)
                    for key in ("tests", "failures", "errors", "skipped")
                }
        if name == "testsuite":
            if active_suite is not None:
                raise ValueError("JUNIT_NESTED_SUITE")
            suite_name = attributes.get("name", "")
            if not suite_name or suite_name in suite_names:
                raise ValueError("JUNIT_DUPLICATE_OR_EMPTY_SUITE_IDENTITY")
            suite_names.add(suite_name)
            active_suite = {
                "declared": {
                    key: integer(attributes, key)
                    for key in ("tests", "failures", "errors", "skipped")
                },
                "start": len(nodes),
            }
        if name == "testcase":
            if current is not None or active_suite is None:
                raise ValueError("JUNIT_NESTED_TESTCASE")
            cases += 1
            if cases > MAX_CASES:
                raise ValueError("JUNIT_CASE_LIMIT_EXCEEDED")
            class_name = attributes.get("classname", "")
            title = attributes.get("name", "")
            file_name = attributes.get("file", "")
            if not title or (not class_name and not file_name):
                raise ValueError("JUNIT_TESTCASE_IDENTITY_INVALID")
            identity = (class_name, file_name.replace("\\", "/"), title)
            if identity in case_identities:
                raise ValueError("JUNIT_DUPLICATE_TESTCASE")
            case_identities.add(identity)
            if not file_name:
                file_name = f"{class_name.replace('.', '/')}.py"
            current = {
                "runner": "pytest",
                "file": file_name.replace("\\", "/"),
                "title": title,
                "status": "passed",
            }
        elif current is not None and name == "failure":
            current["status"] = "failed"
        elif current is not None and name == "error":
            current["status"] = "error"
        elif current is not None and name == "skipped":
            current["status"] = "skipped"

    def end(name: str) -> None:
        nonlocal current, active_suite
        if name == "testcase":
            if current is None:
                raise ValueError("JUNIT_TESTCASE_STRUCTURE_INVALID")
            nodes.append(current)
            current = None
        elif name == "testsuite":
            if active_suite is None:
                raise ValueError("JUNIT_SUITE_STRUCTURE_INVALID")
            suite_nodes = nodes[int(active_suite["start"]):]
            observed_suite = {
                "tests": len(suite_nodes),
                "failures": sum(node["status"] == "failed" for node in suite_nodes),
                "errors": sum(node["status"] == "error" for node in suite_nodes),
                "skipped": sum(node["status"] == "skipped" for node in suite_nodes),
            }
            if not suite_nodes or observed_suite != active_suite["declared"]:
                raise ValueError("JUNIT_SUITE_COUNT_MISMATCH")
            active_suite = None

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = lambda *_args: 0
    parser.SkippedEntityHandler = reject
    try:
        parser.Parse(raw, True)
    except expat.ExpatError as exc:
        raise ValueError("JUNIT_XML_INVALID") from exc
    if current is not None or active_suite is not None or declared is None or not suite_names:
        raise ValueError("JUNIT_TESTCASE_STRUCTURE_INVALID")
    observed = {
        "tests": len(nodes),
        "failures": sum(node["status"] == "failed" for node in nodes),
        "errors": sum(node["status"] == "error" for node in nodes),
        "skipped": sum(node["status"] == "skipped" for node in nodes),
    }
    if observed != declared:
        raise ValueError("JUNIT_COUNT_MISMATCH")
    return nodes


def _read_input(argument: str) -> bytes:
    if argument == "-":
        return sys.stdin.buffer.read(MAX_BYTES + 1)
    path = Path(argument)
    metadata = path.lstat()
    if not path.is_file() or path.is_symlink() or metadata.st_size > MAX_BYTES:
        raise ValueError("JUNIT_FILE_INVALID")
    return path.read_bytes()


def main() -> int:
    if len(sys.argv) != 2:
        print('{"error":"ARGUMENT_INVALID"}')
        return 2
    try:
        nodes = parse_bytes(_read_input(sys.argv[1]))
    except Exception as exc:
        code = str(exc)
        if not code.isascii() or len(code) > 96:
            code = "JUNIT_PARSE_FAILED"
        print(json.dumps({"error": code}, separators=(",", ":")))
        return 1
    print(json.dumps({"nodes": nodes}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
