"""test_derived_artifact_isolation.py — T7 derived 산출물이 학습과 격리됨 (M-60)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "evaluation/card2/derived_artifact_manifest.json"


def test_manifest_exists():
    assert MANIFEST.exists(), "derived_artifact_manifest.json 부재"


def test_derived_artifacts_not_training():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m["is_training_artifact"] is False
    assert m["is_retrieval_or_eval_only"] is True


def test_derived_artifacts_not_under_training_dir():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for a in m["artifacts"]:
        assert not a["path"].startswith("training/"), a["path"]
