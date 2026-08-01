from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from butler_pc_core.learning_capability.canonical_inputs import (
    CanonicalInputError,
    load_approved_inputs,
    preflight_zip,
)


pytestmark = pytest.mark.no_sidecar_token
ROOT = Path(__file__).resolve().parents[2]


def _zip(entries: list[tuple[str, bytes]]) -> io.BytesIO:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries:
            archive.writestr(name, value)
    target.seek(0)
    return target


def test_both_approved_inputs_exist_and_match_approved_sha256():
    approved = load_approved_inputs(
        ROOT / "contracts" / "firstscreen-canonical-inputs.v1.json"
    )
    assert [(item.role, item.sha256) for item in approved] == [
        (
            "algorithm",
            "c09f881056878d209c4b7ba69fd17a615da08728a0d538acc33b8cae17524fb2",
        ),
        (
            "product",
            "6d2a1e0350bc2610b2bc5eae51ca47661a4c8d6ec3bbca0a75043aa03e011632",
        ),
    ]


def test_archive_preflight_rejects_unsafe_entries_before_extraction():
    attacks = [
        [("../escape.txt", b"x")],
        [("/absolute.txt", b"x")],
        [("safe\\escape.txt", b"x")],
        [("safe/NUL.txt", b"x")],
        [("safe/stream:ads", b"x")],
        [("safe/trailing. ", b"x")],
        [("safe/\N{LATIN SMALL LETTER E WITH ACUTE}.txt", b"x"),
         ("safe/e\N{COMBINING ACUTE ACCENT}.txt", b"y")],
    ]
    for entries in attacks:
        with pytest.raises(CanonicalInputError):
            preflight_zip(_zip(entries))
    assert preflight_zip(_zip([("safe/input.json", b"{}")])) == (
        "safe/input.json",
    )


def test_only_one_learning_capability_service_implementation_is_reachable():
    route_source = (
        ROOT / "butler_pc_core" / "sidecar" / "routes" / "learning_capability.py"
    ).read_text(encoding="utf-8")
    implementations = list(
        (ROOT / "butler_pc_core").glob("**/learning_capability/service.py")
    )
    assert implementations == [
        ROOT / "butler_pc_core" / "learning_capability" / "service.py"
    ]
    assert route_source.count("def get_learning_capability_service(") == 1
    assert (
        "from butler_pc_core.learning_capability.service "
        "import LearningCapabilityService"
    ) in route_source
