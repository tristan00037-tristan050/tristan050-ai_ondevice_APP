"""test_manifest_artifact_sha256_present.py — manifest SHA-256 3종 (M-60)."""
from __future__ import annotations

import json
import re
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[3] / "evaluation/card2/derived_artifact_manifest.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def test_each_artifact_has_three_sha256():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m["artifacts"], "artifacts 비어 있음"
    for a in m["artifacts"]:
        for key in ("artifact_sha256", "source_snapshot_sha256", "generator_script_sha256"):
            assert _SHA256.match(a.get(key, "")), f"{a['name']} {key} SHA-256 형식 오류"
