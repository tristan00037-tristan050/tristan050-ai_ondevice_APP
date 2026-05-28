"""Codex P2 regression guard (2026-05-27).

SSOT_V1.md §4-1/§5-2 scope the raw-zero rule to 증빙(evidence): tracked evidence
must keep only meta-only values (numbers/status/ID/version/digests). PR #757's
box3_eval artifacts had stored full model generations (``output``) and source
documents (``input``) as long raw strings.

These tests assert the raw-carrying keys never persist substantial raw text in
any tracked evidence JSON. They deliberately target the raw-carrying keys (the
same keys the repo's verify_no_raw_output_v1.sh guard scans) rather than any
long Korean string, so legitimate analyst meta (diagnosis/recommendation/
qualitative_findings/limitations) is not false-flagged.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "evidence"

# Keys that carry raw model output / source-document content / prompts. Mirrors
# scripts/redact_evidence_raw_text.py: the verify_no_raw_output_v1.sh guard keys
# (prompt/output/raw_input/raw_response) and META_ONLY_BANNED_KEYS
# (text/content/raw_text) plus the eval `input` doc. Provenance keys
# (source/reference, e.g. "PR #741 / path.py") are meta and intentionally excluded.
RAW_FIELDS = ("output", "input", "prompt", "raw_input", "raw_response", "generated_text", "text", "content", "raw_text")
# An excerpt >=50 chars counts as raw again (project excerpt limit).
RAW_THRESHOLD_CHARS = 50


def iter_evidence_json_files():
    if not EVIDENCE_DIR.exists():
        pytest.skip("evidence/ 디렉토리 없음")
    for p in sorted(EVIDENCE_DIR.rglob("*.json")):
        yield p


def _find_raw_in_keys(obj, path=""):
    offenders = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in RAW_FIELDS and isinstance(value, str) and len(value) >= RAW_THRESHOLD_CHARS:
                offenders.append((f"{path}.{key}", len(value)))
            else:
                offenders.extend(_find_raw_in_keys(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            offenders.extend(_find_raw_in_keys(value, f"{path}[{i}]"))
    return offenders


def test_evidence_raw_carrying_keys_have_no_raw_text():
    """No output/input/prompt/source key persists a >=50-char raw string."""
    offenders = []
    for path in iter_evidence_json_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        hits = _find_raw_in_keys(data)
        if hits:
            offenders.append((str(path.relative_to(EVIDENCE_DIR.parent)), hits))
    assert not offenders, f"evidence raw 키에 raw text 잔존: {offenders}"


def test_box3_eval_outputs_are_digested():
    """box3_eval per-case outputs/inputs are stored as sha256 digests, not raw."""
    for name in ("box3_eval/inference_tuning_v1.json", "box3_eval/smoke_eval_v1.json"):
        path = EVIDENCE_DIR / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        serialized = json.dumps(data, ensure_ascii=False)
        assert "_sha256" in serialized, f"{name}: digest(_sha256) 필드 부재 — redaction 미적용"

        def walk(obj):
            if isinstance(obj, dict):
                for raw_key in RAW_FIELDS:
                    if raw_key in obj and isinstance(obj[raw_key], str) and len(obj[raw_key]) >= RAW_THRESHOLD_CHARS:
                        raise AssertionError(f"{name}: '{raw_key}' 필드에 raw text 잔존 (len={len(obj[raw_key])})")
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)

        walk(data)
