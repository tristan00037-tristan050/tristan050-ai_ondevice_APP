from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from butler_pc_core.home.store import (
    ConflictError,
    HomeStore,
    MigrationConflict,
    ReadOnlyError,
    StorageUnavailableError,
    ValidationError,
)


CLIENT_TIME = "2026-07-20T00:00:00Z"


def uid() -> str:
    return str(uuid.uuid4())


def message(message_id: str, role: str, content: str, **extra: object) -> dict[str, object]:
    return {"id": message_id, "role": role, "content": content, "timestamp": CLIENT_TIME, **extra}


def conversation(conversation_id: str = "conversation-1", title: str = "제품 대화") -> dict[str, object]:
    return {
        "id": conversation_id, "folder_id": None, "title": title,
        "title_is_custom": False, "created_at": CLIENT_TIME, "updated_at": CLIENT_TIME,
    }


def legacy(conversation_id: str = "conversation-1", content: str = "민감한 제품 원문") -> dict[str, object]:
    return {**conversation(conversation_id), "messages": [message("message-1", "user", content)]}


def accept(store: HomeStore, *, key: str | None = None, content: str = "사용자 요청") -> dict[str, object]:
    return store.accept_user_turn(
        conversation(), message("user-turn-1", "user", content),
        business_profile_id="profile-a", expected_version=None,
        request_id=uid(), idempotency_key=key or uid(), actor="local-user",
    )


def test_private_app_data_encrypted_message_and_meta_authority(tmp_path: Path) -> None:
    database = tmp_path / "application-data" / "home.sqlite3"
    with HomeStore(database) as store:
        accepted = accept(store, content="민감한 제품 원문")
        assert accepted["command_receipt"]["status"] == "COMMITTED"
        assert stat.S_IMODE(store.location.root.stat().st_mode) == 0o700
        assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
        assert "민감한 제품 원문".encode() not in store.path.read_bytes()
        with sqlite3.connect(store.path) as db:
            authority = db.execute("SELECT installation_id,workspace_id,key_id,schema_version FROM home_meta").fetchone()
            assert authority[1] == store.workspace_id
            assert len(authority[2]) == 64
            assert authority[3] == 3


def test_existing_db_missing_key_never_creates_or_quarantines(tmp_path: Path) -> None:
    database = tmp_path / "home" / "home.sqlite3"
    store = HomeStore(database)
    workspace = store.workspace_id
    accept(store, content="보존되어야 하는 원문")
    store.close()
    store.location.encryption_key.unlink()

    blocked = HomeStore(database, bootstrap_new_install=False)
    try:
        assert blocked.startup_status()["status"] == "READ_ONLY_KEY_MISSING"
        assert blocked.workspace_id == workspace
        assert not blocked.location.encryption_key.exists()
        assert blocked.snapshot()["conversations"][0]["locked"] is True
        assert blocked.messages("conversation-1")["locked"] is True
        with pytest.raises(ReadOnlyError):
            blocked.create_folder("금지", parent_id=None, request_id=uid(), idempotency_key=uid(), actor="local-user")
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT COUNT(*) FROM home_quarantine").fetchone()[0] == 0
    finally:
        blocked.close()


def test_missing_and_conflicting_workspace_mirror_preserve_visible_count(tmp_path: Path) -> None:
    database = tmp_path / "home" / "home.sqlite3"
    store = HomeStore(database)
    workspace = store.workspace_id
    accept(store)
    store.close()
    store.location.workspace_mirror.unlink()

    missing = HomeStore(database, bootstrap_new_install=False)
    assert missing.startup_status()["status"] == "READ_ONLY_WORKSPACE_MIRROR_MISSING"
    assert missing.workspace_id == workspace
    assert len(missing.snapshot()["conversations"]) == 1
    missing.close()

    store.location.workspace_mirror.write_text(str(uuid.uuid4()) + "\n", encoding="ascii")
    store.location.workspace_mirror.chmod(0o600)
    conflict = HomeStore(database, bootstrap_new_install=False)
    assert conflict.startup_status()["status"] == "READ_ONLY_WORKSPACE_CONFLICT"
    assert conflict.workspace_id == workspace
    assert len(conflict.snapshot()["conversations"]) == 1
    conflict.close()


def test_title_nfkc_bidi_controls_and_message_original_semantics(tmp_path: Path) -> None:
    with HomeStore(tmp_path / "home.sqlite3") as store:
        accepted = store.accept_user_turn(
            conversation(title="ＡＢＣ"), message("m1", "user", "코드Ａ≠A\r\n다음 줄"),
            business_profile_id=None, expected_version=None, request_id=uid(), idempotency_key=uid(), actor="local-user",
        )
        assert store.snapshot()["conversations"][0]["title"] == "ABC"
        assert store.messages("conversation-1")["messages"][0]["content"] == "코드Ａ≠A\n다음 줄"
        with pytest.raises(ValidationError, match="INVALID_TITLE"):
            store.rename_conversation("conversation-1", "정상\u202e위장", accepted["conversation_version"], request_id=uid(), idempotency_key=uid(), actor="local-user")
        with pytest.raises(ValidationError, match="MESSAGE_BIDI_CONTROL_FORBIDDEN"):
            store.accept_user_turn(conversation("conversation-2"), message("m2", "user", "위장\u2066내용"), business_profile_id=None, expected_version=None, request_id=uid(), idempotency_key=uid(), actor="local-user")


@pytest.mark.parametrize("score", [-0.1, 1.1, float("nan"), float("inf"), True, -0.0])
def test_score_is_finite_non_bool_unit_interval(tmp_path: Path, score: object) -> None:
    with HomeStore(tmp_path / "home.sqlite3") as store:
        with pytest.raises(ValidationError, match="INVALID_SCORE"):
            store.accept_user_turn(conversation(), message("m1", "user", "x", score=score), business_profile_id=None, expected_version=None, request_id=uid(), idempotency_key=uid(), actor="local-user")


def test_every_mutation_replays_same_response_and_rejects_digest_change(tmp_path: Path) -> None:
    with HomeStore(tmp_path / "home.sqlite3") as store:
        key = uid()
        first = store.create_folder("고객", parent_id=None, request_id=uid(), idempotency_key=key, actor="local-user")
        replay = store.create_folder("고객", parent_id=None, request_id=uid(), idempotency_key=key, actor="local-user")
        assert replay == first
        with pytest.raises(ConflictError, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"):
            store.create_folder("변경", parent_id=None, request_id=uid(), idempotency_key=key, actor="local-user")
        with sqlite3.connect(store.path) as db:
            assert db.execute("SELECT COUNT(*) FROM home_folders WHERE system_kind IS NULL").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM home_commands WHERE operation='create_folder'").fetchone()[0] == 1


def test_durable_turn_and_exactly_one_terminal_are_correlated(tmp_path: Path) -> None:
    with HomeStore(tmp_path / "home.sqlite3") as store:
        accepted = accept(store)
        completed = store.append_assistant_turn(
            "conversation-1", message("assistant-1", "butler", "답변"), accepted["conversation_version"],
            turn_id=accepted["turn_id"], model_request_id=accepted["model_request_id"],
            request_id=uid(), idempotency_key=uid(), actor="local-user",
        )
        assert completed["terminal_count"] == 1
        with pytest.raises(ConflictError, match="TERMINAL_ALREADY_COMMITTED"):
            store.record_terminal(
                "conversation-1", "FAILED", "MODEL_FAILED_AFTER_COMPLETION",
                turn_id=accepted["turn_id"], model_request_id=accepted["model_request_id"],
                request_id=uid(), idempotency_key=uid(), actor="local-user",
            )
        with sqlite3.connect(store.path) as db:
            events = list(db.execute("SELECT turn_id,model_request_id,event_type FROM home_events ORDER BY sequence"))
            assert {row[0] for row in events} == {accepted["turn_id"]}
            assert {row[1] for row in events} == {accepted["model_request_id"]}
            assert sum(row[2].startswith("MODEL_") and row[2] != "MODEL_REQUEST_PENDING" for row in events) == 1


def test_restart_reconciler_commits_one_failed_terminal(tmp_path: Path) -> None:
    database = tmp_path / "home" / "home.sqlite3"
    store = HomeStore(database)
    accepted = accept(store)
    store.close()
    restarted = HomeStore(database, bootstrap_new_install=False)
    try:
        with sqlite3.connect(database) as db:
            terminals = db.execute(
                "SELECT COUNT(*) FROM home_events WHERE model_request_id=? AND event_type='MODEL_FAILED'",
                (accepted["model_request_id"],),
            ).fetchone()[0]
            assert terminals == 1
        assert restarted.reconcile_interrupted_requests()["pending"] == 0
    finally:
        restarted.close()


def test_profile_snapshot_filter_and_explicit_audited_reassignment(tmp_path: Path) -> None:
    with HomeStore(tmp_path / "home.sqlite3") as store:
        accepted = accept(store)
        assert store.snapshot(profile_id="profile-a")["filtered_conversation_count"] == 1
        assert store.snapshot(profile_id="profile-b")["filtered_conversation_count"] == 0
        changed = store.reassign_profile(
            "conversation-1", "profile-b", accepted["conversation_version"], request_id=uid(),
            idempotency_key=uid(), actor="local-user",
        )
        assert changed["business_profile_id"] == "profile-b"
        with sqlite3.connect(store.path) as db:
            assert db.execute("SELECT COUNT(*) FROM home_audit WHERE action='REASSIGN_PROFILE'").fetchone()[0] == 1


def test_migration_is_inventory_exact_and_conflict_rolls_back(tmp_path: Path) -> None:
    with HomeStore(tmp_path / "home.sqlite3") as store:
        key = uid()
        receipt = store.migrate_legacy([legacy()], migration_id="legacy-v2", request_id=uid(), idempotency_key=key, actor="local-user")
        replay = store.migrate_legacy([legacy()], migration_id="legacy-v2", request_id=uid(), idempotency_key=key, actor="local-user")
        assert replay == receipt
        assert receipt["exact_import"] is True
        with pytest.raises(ConflictError, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"):
            store.migrate_legacy([legacy(content="변경")], migration_id="legacy-v2", request_id=uid(), idempotency_key=key, actor="local-user")
        with pytest.raises(MigrationConflict):
            store.migrate_legacy([legacy(content="충돌")], migration_id="other", request_id=uid(), idempotency_key=uid(), actor="local-user")
        assert store.messages("conversation-1")["messages"][0]["content"] == "민감한 제품 원문"


def test_schema_upgrade_creates_immutable_backup_and_manifest(tmp_path: Path) -> None:
    database = tmp_path / "home" / "home.sqlite3"
    store = HomeStore(database)
    accept(store)
    store.close()
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA user_version=2")
        db.commit()
    upgraded = HomeStore(database, bootstrap_new_install=False)
    upgraded.close()
    backups = list((database.parent / "backups").glob("*.sqlite3"))
    manifests = list((database.parent / "backups").glob("*.manifest.json"))
    assert len(backups) == len(manifests) == 1
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600
    assert json.loads(manifests[0].read_text())["integrity_result"] == "PASS"


def test_storage_symlink_and_mode_widening_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "home" / "home.sqlite3"
    store = HomeStore(database)
    store.close()
    database.chmod(0o644)
    widened = HomeStore(database, bootstrap_new_install=False)
    assert widened.startup_status()["status"] == "READ_ONLY_STORAGE_GUARD_FAILED"
    widened.close()
    database.chmod(0o600)
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(StorageUnavailableError, match="HOME_STORAGE_SYMLINK_FORBIDDEN"):
        HomeStore(link / "home.sqlite3")


def test_new_install_is_staged_and_retries_after_atomic_publish_failure(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "home" / "home.sqlite3"
    real_replace = os.replace

    def fail_publish(source: os.PathLike[str] | str, destination: os.PathLike[str] | str) -> None:
        if Path(source).name == ".home.installing" and Path(destination) == database.parent:
            raise OSError("injected atomic publish failure")
        real_replace(source, destination)

    monkeypatch.setattr("butler_pc_core.home.store.os.replace", fail_publish)
    with pytest.raises(StorageUnavailableError, match="HOME_NEW_INSTALL_ATOMIC_FAILED"):
        HomeStore(database)
    assert not database.parent.exists()
    assert not (tmp_path / ".home.installing").exists()

    monkeypatch.setattr("butler_pc_core.home.store.os.replace", real_replace)
    with HomeStore(database) as store:
        assert store.startup_status()["status"] == "HOME_READY"
        assert database.exists()
        assert not (database.parent / ".installing.json").exists()


@pytest.mark.skipif(os.name == "nt", reason="fork-based process lock test")
def test_second_process_writer_is_blocked(tmp_path: Path) -> None:
    database = tmp_path / "home" / "home.sqlite3"
    store = HomeStore(database)
    script = """
from pathlib import Path
from butler_pc_core.home.store import HomeStore
HomeStore(Path({path!r}), bootstrap_new_install=False)
""".format(path=str(database))
    result = subprocess.run([sys.executable, "-c", script], text=True, capture_output=True, env={**os.environ, "PYTHONPATH": str(Path.cwd())})
    store.close()
    assert result.returncode != 0
    assert "HOME_INSTANCE_ALREADY_RUNNING" in result.stderr


def test_runtime_truth_separates_missing_policy_and_measurement(tmp_path: Path) -> None:
    with HomeStore(tmp_path / "home.sqlite3") as store:
        status = store.runtime_status()
        assert status["policy"]["status"] == "UNKNOWN"
        assert status["measurement"]["status"] == "NOT_MEASURED"
        assert status["runtime_activation_allowed"] is False
