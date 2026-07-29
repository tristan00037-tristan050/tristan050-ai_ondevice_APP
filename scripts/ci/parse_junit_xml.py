from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.parsers import expat


MAX_SUITES = 2_048
MAX_CASES = 100_000
MAX_ATTRIBUTES = 64
MAX_ATTRIBUTE_CHARS = 16_384


def parse(path: Path) -> list[dict[str, str]]:
    parser = expat.ParserCreate("utf-8")
    parser.buffer_text = True
    suites = 0
    cases = 0
    current: dict[str, str] | None = None
    nodes: list[dict[str, str]] = []
    root_counts: dict[str, int] | None = None

    def reject(*_args):
        raise ValueError("JUNIT_DTD_OR_ENTITY_FORBIDDEN")

    def start(name: str, attributes: dict[str, str]) -> None:
        nonlocal suites, cases, current, root_counts
        if (
            len(attributes) > MAX_ATTRIBUTES
            or sum(len(key) + len(value) for key, value in attributes.items())
            > MAX_ATTRIBUTE_CHARS
        ):
            raise ValueError("JUNIT_ATTRIBUTE_LIMIT_EXCEEDED")
        if name in {"testsuite", "testsuites"}:
            if suites == 0 and "tests" in attributes:
                try:
                    root_counts = {
                        key: int(attributes.get(key, "0"))
                        for key in ("tests", "failures", "errors", "skipped")
                    }
                except ValueError as exc:
                    raise ValueError("JUNIT_COUNT_INVALID") from exc
                if any(value < 0 for value in root_counts.values()):
                    raise ValueError("JUNIT_COUNT_INVALID")
            suites += 1
            if suites > MAX_SUITES:
                raise ValueError("JUNIT_SUITE_LIMIT_EXCEEDED")
        if name == "testcase":
            if current is not None:
                raise ValueError("JUNIT_NESTED_TESTCASE")
            cases += 1
            if cases > MAX_CASES:
                raise ValueError("JUNIT_CASE_LIMIT_EXCEEDED")
            class_name = attributes.get("classname", "")
            title = attributes.get("name", "")
            file_name = attributes.get("file", "")
            if not title or (not class_name and not file_name):
                raise ValueError("JUNIT_TESTCASE_IDENTITY_INVALID")
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
        nonlocal current
        if name == "testcase":
            if current is None:
                raise ValueError("JUNIT_TESTCASE_STRUCTURE_INVALID")
            nodes.append(current)
            current = None

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = lambda *_args: 0
    parser.SkippedEntityHandler = reject
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("JUNIT_BOM_FORBIDDEN")
    parser.Parse(raw, True)
    if current is not None:
        raise ValueError("JUNIT_TESTCASE_STRUCTURE_INVALID")
    if root_counts is not None:
        observed = {
            "tests": len(nodes),
            "failures": sum(node["status"] == "failed" for node in nodes),
            "errors": sum(node["status"] == "error" for node in nodes),
            "skipped": sum(node["status"] == "skipped" for node in nodes),
        }
        if observed != root_counts:
            raise ValueError("JUNIT_COUNT_MISMATCH")
    return nodes


def main() -> int:
    if len(sys.argv) != 2:
        print('{"error":"ARGUMENT_INVALID"}')
        return 2
    try:
        nodes = parse(Path(sys.argv[1]))
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
