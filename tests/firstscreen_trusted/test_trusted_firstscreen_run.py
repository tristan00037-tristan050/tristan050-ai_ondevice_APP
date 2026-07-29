from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_sidecar_token

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ci" / "trusted_firstscreen_run.py"
SPEC = importlib.util.spec_from_file_location("trusted_firstscreen_run", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
WORKFLOW_NAME = "firstscreen-v2-5-product-gate"
WORKFLOW_PATH = ".github/workflows/firstscreen-v2-5.yml"
HEAD = "a" * 40
TREE = "b" * 40
ARTIFACT = b"artifact bytes"


class FakeApi:
    def __init__(self, *, artifact_digest: str | None = None) -> None:
        self._digest = artifact_digest or hashlib.sha256(ARTIFACT).hexdigest()
        self.responses = {
            f"/repos/{REPOSITORY}/pulls/886": {
                "number": 886,
                "head": {"sha": HEAD},
            },
            f"/repos/{REPOSITORY}/actions/workflows/7": {
                "id": 7,
                "name": WORKFLOW_NAME,
                "path": WORKFLOW_PATH,
                "state": "active",
            },
            f"/repos/{REPOSITORY}/git/commits/{HEAD}": {
                "sha": HEAD,
                "tree": {"sha": TREE},
            },
            f"/repos/{REPOSITORY}/actions/runs/123/artifacts?per_page=100": {
                "total_count": 1,
                "artifacts": [
                    {
                        "id": 456,
                        "name": f"firstscreen-v9-evidence-{HEAD}",
                        "expired": False,
                        "digest": f"sha256:{self._digest}",
                    }
                ]
            },
        }

    def json(self, path: str):
        return self.responses[path]

    def download(self, path: str, output: Path) -> str:
        assert path == f"/repos/{REPOSITORY}/actions/artifacts/456/zip"
        output.write_bytes(ARTIFACT)
        return hashlib.sha256(ARTIFACT).hexdigest()


def _event() -> dict:
    return {
        "repository": {"full_name": REPOSITORY},
        "workflow_run": {
            "id": 123,
            "run_attempt": 2,
            "workflow_id": 7,
            "name": WORKFLOW_NAME,
            "event": "pull_request",
            "conclusion": "success",
            "head_sha": HEAD,
            "head_repository": {"full_name": REPOSITORY},
            "pull_requests": [{"number": 886}],
        },
    }


def _resolve(tmp_path: Path, event: dict, api: FakeApi):
    return MODULE.resolve_run(
        event,
        api,
        repository=REPOSITORY,
        workflow_name=WORKFLOW_NAME,
        workflow_path=WORKFLOW_PATH,
        artifact_prefix="firstscreen-v9-evidence-",
        artifact_output=tmp_path / "artifact.zip",
        trusted_head="c" * 40,
        trusted_tree="d" * 40,
        trusted_workflow_ref=f"{REPOSITORY}/trusted@refs/heads/main",
    )


def test_successful_run_binds_pr_head_tree_workflow_and_artifact(
    tmp_path: Path,
) -> None:
    metadata, event = _resolve(tmp_path, _event(), FakeApi())
    assert metadata["subject_head"] == HEAD
    assert metadata["tree_oid"] == {"algorithm": "sha1", "hex": TREE}
    assert metadata["producer"]["run_id"] == "123"
    assert metadata["producer"]["run_attempt"] == 2
    assert metadata["artifact"]["id"] == 456
    assert event["pull_request"]["head"]["sha"] == HEAD


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("conclusion", "failure", "UPSTREAM_RUN_INVALID"),
        ("event", "push", "UPSTREAM_RUN_INVALID"),
        ("name", "lookalike", "UPSTREAM_RUN_INVALID"),
    ],
)
def test_noncanonical_upstream_run_is_rejected(
    tmp_path: Path,
    field: str,
    value: str,
    code: str,
) -> None:
    event = _event()
    event["workflow_run"][field] = value
    with pytest.raises(MODULE.RunError, match=code):
        _resolve(tmp_path, event, FakeApi())


def test_fork_artifact_is_rejected(tmp_path: Path) -> None:
    event = _event()
    event["workflow_run"]["head_repository"]["full_name"] = "attacker/fork"
    with pytest.raises(MODULE.RunError, match="FORK_ARTIFACT_NOT_ALLOWED"):
        _resolve(tmp_path, event, FakeApi())


def test_github_artifact_digest_mismatch_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(MODULE.RunError, match="ARTIFACT_DIGEST_MISMATCH"):
        _resolve(tmp_path, _event(), FakeApi(artifact_digest="f" * 64))
