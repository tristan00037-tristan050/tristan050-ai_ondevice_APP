from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts" / "ci" / "helper1_canonical_subject.py"
S1 = "1" * 40
S2 = "2" * 40
WORKFLOW = "tristan00037-tristan050/tristan050-ai_ondevice_APP/.github/workflows/helper1-v2-evidence.yml@refs/heads/main"


_SPEC = importlib.util.spec_from_file_location("helper1_canonical_subject", PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _module():
    return _MODULE


def _repo():
    return {"id": 1097940756, "full_name": "tristan00037-tristan050/tristan050-ai_ondevice_APP"}


def _subject(name, event, **kwargs):
    return _module().canonical_subject(
        name,
        event,
        expected_repository_id=1097940756,
        expected_repository_full_name="tristan00037-tristan050/tristan050-ai_ondevice_APP",
        workflow_ref=WORKFLOW,
        workflow_sha="f" * 40,
        **kwargs,
    )


def _pr(action="opened", sha=S1, head_repo=None, number=7):
    return {
        "repository": _repo(),
        "action": action,
        "number": number,
        "pull_request": {
            "head": {
                "sha": sha,
                "repo": {"full_name": head_repo or _repo()["full_name"]},
            }
        },
    }


def test_same_repo_and_fork_pull_requests_bind_head_not_merge_sha():
    same = _pr()
    same["after"] = S2
    assert _subject("pull_request", same).subject_sha == S1
    fork = _subject("pull_request", _pr(head_repo="forker/tristan050-ai_ondevice_APP"))
    assert fork.subject_repository_full_name == "forker/tristan050-ai_ondevice_APP"


def test_synchronize_rerun_merge_group_and_protected_push_are_deterministic():
    synchronized = _subject("pull_request", _pr(action="synchronize", sha=S2))
    assert synchronized.subject_sha == S2
    assert synchronized == _subject("pull_request", _pr(action="synchronize", sha=S2))
    group = _subject("merge_group", {
        "repository": _repo(),
        "action": "checks_requested",
        "merge_group": {"head_sha": S2, "head_ref": "refs/heads/gh-readonly-queue/main/x"},
    })
    assert group.subject_sha == S2 and group.approval_eligible
    push = _subject("push", {
        "repository": _repo(), "after": S1, "ref": "refs/heads/main", "deleted": False,
    })
    assert push.approval_eligible


def test_dispatch_is_diagnostic_and_workflow_run_is_never_a_product_subject():
    dispatch = _subject(
        "workflow_dispatch",
        {"repository": _repo(), "ref": "refs/heads/main"},
        dispatch_sha=S1,
    )
    assert not dispatch.approval_eligible
    with pytest.raises(_module().SubjectError, match="BLOCK_EVENT_UNSUPPORTED"):
        _subject("workflow_run", {"repository": _repo()})


@pytest.mark.parametrize(
    "event",
    [
        _pr(sha="A" * 40),
        _pr(sha="1" * 39),
        _pr(sha="0" * 40),
        {"repository": {"id": True, "full_name": _repo()["full_name"]}, "after": S1, "ref": "refs/heads/main"},
    ],
)
def test_bad_sha_and_boolean_repository_id_are_blocked(event):
    name = "pull_request" if "pull_request" in event else "push"
    with pytest.raises(_module().SubjectError):
        _subject(name, event)


def test_deleted_or_unprotected_push_and_missing_pr_head_are_blocked():
    for event in (
        {"repository": _repo(), "after": S1, "ref": "refs/heads/main", "deleted": True},
        {"repository": _repo(), "after": S1, "ref": "refs/heads/dev", "deleted": False},
    ):
        with pytest.raises(_module().SubjectError, match="BLOCK_EVENT_UNSUPPORTED"):
            _subject("push", event)
    broken = _pr()
    broken["pull_request"] = {}
    with pytest.raises(_module().SubjectError, match="BLOCK_EVENT_SCHEMA"):
        _subject("pull_request", broken)


def test_repository_and_workflow_provenance_mismatch_are_blocked():
    changed = _pr()
    changed["repository"] = {"id": 1, "full_name": _repo()["full_name"]}
    with pytest.raises(_module().SubjectError, match="BLOCK_REPOSITORY_MISMATCH"):
        _subject("pull_request", changed)
    module = _module()
    with pytest.raises(module.SubjectError, match="BLOCK_WORKFLOW_PROVENANCE"):
        module.canonical_subject(
            "pull_request",
            _pr(),
            expected_repository_id=1097940756,
            expected_repository_full_name=_repo()["full_name"],
            workflow_ref="bad ref",
            workflow_sha="f" * 40,
        )
