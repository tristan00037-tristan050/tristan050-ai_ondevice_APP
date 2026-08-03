from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts" / "ci" / "helper1_subject_binding.py"
SPEC = importlib.util.spec_from_file_location("helper1_subject_binding_v4", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
SHA = "1" * 40


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _subject() -> dict[str, object]:
    return {
        "schema_version": "butler.helper1.canonical-subject.v1",
        "event_name": "pull_request",
        "event_action": "synchronize",
        "repository_id": 1097940756,
        "repository_full_name": REPOSITORY,
        "subject_repository_full_name": "fork-owner/tristan050-ai_ondevice_APP",
        "subject_sha": SHA,
        "pull_request_number": 17,
        "merge_group_head_ref": None,
        "protected_ref": None,
        "workflow_ref": f"{REPOSITORY}/.github/workflows/helper1-v2-evidence.yml@refs/heads/main",
        "workflow_sha": "2" * 40,
        "approval_eligible": True,
    }


def _event() -> dict[str, object]:
    return {
        "repository": {"id": 1097940756, "full_name": REPOSITORY},
        "workflow_run": {
            "id": 99,
            "run_attempt": 2,
            "name": "helper1-v2-evidence-producer",
            "path": ".github/workflows/helper1-v2-evidence.yml",
            "conclusion": "success",
            "event": "pull_request",
            "head_sha": SHA,
            "pull_requests": [{"number": 17}],
        },
    }


def test_protected_verifier_requeries_current_fork_pr_head(tmp_path: Path) -> None:
    event = _write(tmp_path / "event.json", _event())
    subject = _write(tmp_path / "subject.json", _subject())
    observed = MODULE.verify_canonical_subject(
        event,
        subject,
        api_get=lambda _path: {
            "head": {
                "sha": SHA,
                "repo": {"full_name": "fork-owner/tristan050-ai_ondevice_APP"},
            }
        },
    )
    assert observed["subject_sha"] == SHA


def test_stale_head_repository_swap_and_workflow_run_sha_confusion_are_blocked(
    tmp_path: Path,
) -> None:
    event_value = _event()
    event = _write(tmp_path / "event.json", event_value)
    subject = _write(tmp_path / "subject.json", _subject())
    with pytest.raises(MODULE.SubjectBindingError, match="BLOCK_PR_HEAD_STALE"):
        MODULE.verify_canonical_subject(
            event,
            subject,
            api_get=lambda _path: {
                "head": {"sha": "3" * 40, "repo": {"full_name": "attacker/repo"}}
            },
        )
    event_value["workflow_run"]["head_sha"] = "4" * 40
    _write(event, event_value)
    with pytest.raises(MODULE.SubjectBindingError, match="BLOCK_SUBJECT_SHA_MISMATCH"):
        MODULE.verify_canonical_subject(
            event,
            subject,
            api_get=lambda _path: {},
        )
