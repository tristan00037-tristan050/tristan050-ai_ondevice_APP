from __future__ import annotations

from pathlib import Path

from butler_pc_core.learning_core.index_manifest import IndexManifest
from butler_pc_core.learning_core.queue import ArtifactQueue
from butler_pc_core.learning_core.contracts import stable_json_digest
from tests.learning_core.test_integrated_learning_gate import _candidate, _digest


def test_artifact_queue_is_digest_only_and_idempotent(tmp_path: Path):
    queue = ArtifactQueue(tmp_path / "queue.jsonl")
    candidate = _candidate()
    first = queue.append_candidate(candidate)
    second = queue.append_candidate(candidate)
    assert first.appended is True
    assert second.appended is False
    assert second.reason == "IDEMPOTENT_DUPLICATE"
    records = queue.read_records()
    assert len(records) == 1
    assert records[0]["auto_apply_to_runtime"] is False
    text = (tmp_path / "queue.jsonl").read_text(encoding="utf-8")
    assert "사내 자금이동" not in text
    assert "raw_memo" not in text


def test_artifact_queue_marks_same_id_new_digest_as_replaced(tmp_path: Path):
    queue = ArtifactQueue(tmp_path / "queue.jsonl")
    candidate = _candidate()
    queue.append_candidate(candidate)
    changed = _candidate()
    changed["payload"] = dict(changed["payload"], tests_to_run=["python3 -m pytest tests/accounting -q"])
    changed["payload_digest"] = stable_json_digest(changed["payload"])
    result = queue.append_candidate(changed)
    assert result.appended is True
    records = queue.read_records()
    assert len(records) == 2
    assert records[-1]["queue_status"] == "replaced"
    assert records[-1]["previous_candidate_digest"] == records[0]["candidate_digest"]


def test_artifact_queue_preserves_removed_status_for_retraction(tmp_path: Path):
    queue = ArtifactQueue(tmp_path / "queue.jsonl")
    candidate = _candidate()
    queue.append_candidate(candidate)
    removed = _candidate()
    removed["payload"] = dict(removed["payload"], tests_to_run=["python3 -m pytest tests/accounting -q"])
    removed["payload_digest"] = stable_json_digest(removed["payload"])

    result = queue.append_candidate(removed, status="removed")

    assert result.appended is True
    records = queue.read_records()
    assert len(records) == 2
    assert records[-1]["queue_status"] == "removed"
    assert records[-1]["previous_candidate_digest"] == records[0]["candidate_digest"]


def test_index_manifest_has_previous_pointer_and_digest():
    manifest = IndexManifest.build(
        manifest_id="ilm-001",
        target_kind="folder_doc",
        candidate_digests=[_digest("candidate-a")],
        previous_manifest_digest=_digest("previous"),
        rollback_ref="keyring://rollback/ilm-000",
    ).to_dict()
    assert manifest["previous_manifest_digest"] == _digest("previous")
    assert manifest["rollback_ref"] == "keyring://rollback/ilm-000"
    assert manifest["auto_apply_to_runtime"] is False
    assert manifest["manifest_digest"].startswith("sha256:")
