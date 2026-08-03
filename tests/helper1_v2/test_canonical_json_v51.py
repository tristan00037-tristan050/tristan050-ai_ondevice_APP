from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from butler_pc_core.helper1.canonical_json import (
    CanonicalJsonError,
    canonicalize_butler_cj1,
    loads_butler_cj1,
    require_canonical_butler_cj1,
)

VECTOR_ROOT = Path(__file__).with_name("vectors")


def test_butler_cj1_golden_vector_is_stable() -> None:
    value = {"e\u0301": "\ud55c", "a": [1, True, None]}
    expected = '{"a":[1,true,null],"\u00e9":"\ud55c"}'.encode("utf-8")
    assert canonicalize_butler_cj1(value) == expected
    assert require_canonical_butler_cj1(expected) == {"a": [1, True, None], "\u00e9": "\ud55c"}


@pytest.mark.parametrize(
    "raw,code",
    [
        (b'{"a":1,"a":2}', "CJ1_DUPLICATE_KEY"),
        ('{"e\\u0301":1,"\\u00e9":2}'.encode(), "CJ1_NORMALIZED_KEY_COLLISION"),
        (b'{"a":1.0}', "CJ1_FLOAT_FORBIDDEN"),
        (b'{"a":1e2}', "CJ1_FLOAT_FORBIDDEN"),
        (b'{"a":9223372036854775808}', "CJ1_INTEGER_OUT_OF_RANGE"),
        (b'\xef\xbb\xbf{}', "CJ1_BYTES_INVALID"),
        (b'{"a":"\\ud800"}', "CJ1_STRING_INVALID"),
    ],
)
def test_butler_cj1_rejects_ambiguous_inputs(raw: bytes, code: str) -> None:
    with pytest.raises(CanonicalJsonError, match=code):
        loads_butler_cj1(raw)


def test_butler_cj1_requires_existing_bytes_to_be_canonical() -> None:
    with pytest.raises(CanonicalJsonError, match="CJ1_NON_CANONICAL_BYTES"):
        require_canonical_butler_cj1(b'{"b":2, "a":1}')


def test_shared_canonical_vector_file_drives_bytes_and_failures() -> None:
    vectors = json.loads((VECTOR_ROOT / "canonical_json_v1.json").read_text(encoding="utf-8"))
    assert vectors["schema_version"] == "butler.helper1.canonical-json-vectors.v1"
    for vector in vectors["vectors"]:
        value = loads_butler_cj1(vector["raw_utf8"].encode("utf-8"))
        encoded = canonicalize_butler_cj1(value)
        assert encoded == vector["canonical_utf8"].encode("utf-8")
        assert hashlib.sha256(encoded).hexdigest() == vector["canonical_sha256"]
    for vector in vectors["rejections"]:
        with pytest.raises(CanonicalJsonError, match=vector["error_code"]):
            loads_butler_cj1(vector["raw_utf8"].encode("utf-8"))
