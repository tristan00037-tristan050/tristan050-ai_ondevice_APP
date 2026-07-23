from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from butler_pc_core.a4_verifier.canonical import (
    CanonicalError,
    attestation_envelope,
    jcs_bytes,
)


FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "a4_authority_v53"
    / "canonical_vectors.json"
)


def test_v53_committed_canonical_vectors() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "butler.box5.a4.canonical_vectors.v5.3"
    for vector in payload["vectors"]:
        canonical = jcs_bytes(vector["value"])
        assert canonical.hex() == vector["canonical_hex"], vector["id"]
        assert hashlib.sha256(canonical).hexdigest() == vector["canonical_sha256"]
        assert (
            hashlib.sha256(attestation_envelope(canonical)).hexdigest()
            == vector["envelope_sha256"]
        )


@pytest.mark.parametrize("value", [1.0, float("nan"), float("inf")])
def test_v53_integer_only_profile_rejects_floats(value: float) -> None:
    with pytest.raises(CanonicalError, match="BLOCK_REQUEST_SCHEMA"):
        jcs_bytes({"value": value})
