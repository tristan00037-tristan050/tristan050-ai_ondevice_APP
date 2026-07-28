from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from butler_pc_core.app_data import AppDataPathError, product_data_root
from butler_pc_core.learning_capability.generation_store import (
    DurableGenerationStore,
    GenerationStoreError,
)
from butler_pc_core.learning_capability.strict_json import (
    MAX_JSON_BYTES,
    StrictJsonError,
    canonical_json_bytes,
    load_strict_bytes,
)
from butler_pc_core.learning_capability.trusted_state import (
    TrustedStateError,
    TrustedStateFile,
)


pytestmark = pytest.mark.no_sidecar_token


@pytest.mark.parametrize(
    ("raw_values", "code"),
    [
        ((b'{"a":1,"a":2}',), "JSON_DUPLICATE_KEY"),
        ((b'{"a":{"b":1,"b":2}}',), "JSON_DUPLICATE_KEY"),
        (
            (b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}'),
            "JSON_NON_FINITE_FORBIDDEN",
        ),
        ((b"\xff", b"\xef\xbb\xbf{}"), None),
        ((b"[]", b'"text"', b"1", b"null"), "JSON_ROOT_NOT_OBJECT"),
        ((b'{"a":"\\ud800"}',), "JSON_UNPAIRED_SURROGATE"),
    ],
    ids=(
        "FSV10-JSON-001",
        "FSV10-JSON-002",
        "FSV10-JSON-003",
        "FSV10-JSON-004",
        "FSV10-JSON-005",
        "FSV10-JSON-008",
    ),
)
def test_strict_json_rejects_ambiguous_or_noncanonical_inputs(
    raw_values,
    code,
):
    for raw in raw_values:
        expected = code
        if expected is None:
            expected = (
                "JSON_BOM_FORBIDDEN"
                if raw.startswith(b"\xef\xbb\xbf")
                else "JSON_UTF8_INVALID"
            )
        with pytest.raises(StrictJsonError, match=expected):
            load_strict_bytes(raw)


def test_strict_json_rejects_oversized_input_before_decode():
    with pytest.raises(StrictJsonError, match="JSON_TOO_LARGE"):
        load_strict_bytes(b"{" + b" " * MAX_JSON_BYTES + b"}")


def test_strict_json_enforces_depth_node_and_string_limits():
    deep: object = 0
    for _index in range(17):
        deep = {"a": deep}
    with pytest.raises(StrictJsonError, match="JSON_TOO_DEEP"):
        load_strict_bytes(json.dumps(deep).encode("utf-8"))
    with pytest.raises(StrictJsonError, match="JSON_TOO_COMPLEX"):
        load_strict_bytes(
            json.dumps({"nodes": [0] * 2050}).encode("utf-8")
        )
    with pytest.raises(StrictJsonError, match="JSON_STRING_TOO_LONG"):
        load_strict_bytes(
            json.dumps({"text": "x" * 8193}).encode("utf-8")
        )


def test_generation_json_rejects_bool_float_negative_and_unsafe_integer(
    tmp_path,
):
    path = tmp_path / "generation.json"
    invalid_generations = (
        b"true",
        b"false",
        b"1.25",
        b"-1",
        b"9007199254740992",
    )
    for generation in invalid_generations:
        payload = (
            b'{"schema_version":1,"last_generation":'
            + generation
            + b',"last_snapshot_digest":"'
            + b"a" * 64
            + b'"}'
        )
        _write_private(path, payload)
        with pytest.raises(GenerationStoreError):
            DurableGenerationStore(path).generation_for("b" * 64)


def test_generation_json_rejects_unknown_schema_key(tmp_path):
    path = tmp_path / "generation.json"
    _write_private(
        path,
        b'{"schema_version":1,"last_generation":1,'
        b'"last_snapshot_digest":"' + b"a" * 64 + b'","extra":1}',
    )
    with pytest.raises(GenerationStoreError):
        DurableGenerationStore(path).generation_for("b" * 64)


def test_strict_json_rejects_integer_digit_overflow():
    with pytest.raises(StrictJsonError, match="JSON_INTEGER_TOO_LARGE"):
        load_strict_bytes(b'{"value":123456789012345678901}')


def test_strict_json_canonical_round_trip_is_stable():
    value = {"z": [True, None, 3], "a": {"text": "한글"}}
    raw = canonical_json_bytes(value)
    assert raw == b'{"a":{"text":"\xed\x95\x9c\xea\xb8\x80"},"z":[true,null,3]}'
    assert load_strict_bytes(raw) == value


def _write_private(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    path.chmod(0o600)


def test_trusted_state_rejects_final_file_symlink(tmp_path):
    target = tmp_path / "target.json"
    _write_private(target, b"{}")
    final_root = tmp_path / "final-root"
    final_root.mkdir(mode=0o700)
    (final_root / "state.json").symlink_to(target)
    state = TrustedStateFile(final_root / "state.json", max_file_bytes=128)
    with pytest.raises(TrustedStateError):
        with state.locked() as session:
            session.read_json_optional()


def test_trusted_state_rejects_intermediate_directory_symlink(tmp_path):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    state = TrustedStateFile(linked / "state.json", max_file_bytes=128)
    with pytest.raises(TrustedStateError):
        with state.locked():
            pass


def test_open_directory_descriptor_resists_parent_path_replacement(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir(mode=0o700)
    _write_private(root / "state.json", b'{"source":"original"}')
    state = TrustedStateFile(root / "state.json", max_file_bytes=128)
    with state.locked() as session:
        moved = tmp_path / "trusted-original"
        root.rename(moved)
        root.mkdir(mode=0o700)
        _write_private(root / "state.json", b'{"source":"replacement"}')
        assert session.read_json_optional() == {"source": "original"}


def test_trusted_state_rejects_non_regular_file_types(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir(mode=0o700)
    directory_target = root / "directory.json"
    directory_target.mkdir()
    state = TrustedStateFile(directory_target, max_file_bytes=128)
    with pytest.raises(TrustedStateError):
        with state.locked() as session:
            session.read_json_optional()

    fifo = root / "fifo.json"
    os.mkfifo(fifo, 0o600)
    state = TrustedStateFile(fifo, max_file_bytes=128)
    with pytest.raises(TrustedStateError, match="FILE_TYPE"):
        with state.locked() as session:
            session.read_json_optional()


def test_trusted_state_rejects_foreign_owner(monkeypatch):
    from butler_pc_core.learning_capability import trusted_state

    metadata = os.stat(__file__)
    fields = list(metadata)
    fields[4] = os.geteuid() + 1
    foreign = os.stat_result(fields)
    with pytest.raises(TrustedStateError, match="OWNER"):
        trusted_state._validate_file(foreign, max_bytes=1024)


def test_trusted_state_requires_exact_private_file_permissions(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir(mode=0o700)
    wide = root / "wide.json"
    _write_private(wide, b"{}")
    wide.chmod(0o640)
    state = TrustedStateFile(wide, max_file_bytes=128)
    with pytest.raises(TrustedStateError, match="PERMISSIONS"):
        with state.locked() as session:
            session.read_json_optional()


def test_trusted_state_rejects_hardlinked_state_file(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir(mode=0o700)
    primary = root / "primary.json"
    linked = root / "hardlink.json"
    _write_private(primary, b"{}")
    os.link(primary, linked)
    state = TrustedStateFile(primary, max_file_bytes=128)
    with pytest.raises(TrustedStateError, match="LINK_COUNT"):
        with state.locked() as session:
            session.read_json_optional()


def test_trusted_state_rejects_oversized_file_with_bounded_read(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir(mode=0o700)
    oversized = root / "oversized.json"
    _write_private(oversized, b"x" * 129)
    state = TrustedStateFile(oversized, max_file_bytes=128)
    with pytest.raises(TrustedStateError, match="TOO_LARGE"):
        with state.locked() as session:
            session.read_json_optional()


def test_trusted_state_rejects_group_or_other_writable_root(tmp_path):
    writable = tmp_path / "writable"
    writable.mkdir(mode=0o770)
    writable.chmod(0o770)
    state = TrustedStateFile(writable / "state.json", max_file_bytes=128)
    with pytest.raises(TrustedStateError, match="DIRECTORY_PERMISSIONS"):
        with state.locked():
            pass


def test_trusted_state_lock_timeout_is_bounded(tmp_path):
    state = TrustedStateFile(
        tmp_path / "trusted" / "state.json",
        max_file_bytes=128,
        lock_timeout_seconds=0.05,
    )
    captured: list[BaseException] = []

    def contend() -> None:
        try:
            with state.locked():
                pass
        except BaseException as exc:
            captured.append(exc)

    with state.locked():
        thread = threading.Thread(target=contend)
        thread.start()
        thread.join(timeout=1)
    assert not thread.is_alive()
    assert len(captured) == 1
    assert "TRUST_STATE_LOCK_TIMEOUT" in str(captured[0])


def test_trusted_state_rejects_relative_or_missing_app_data_root(
    monkeypatch,
):
    with pytest.raises(TrustedStateError, match="ROOT_NOT_ABSOLUTE"):
        TrustedStateFile(Path("relative.json"), max_file_bytes=128)
    monkeypatch.setenv("BUTLER_APP_DATA_DIR", "relative")
    with pytest.raises(AppDataPathError, match="NOT_ABSOLUTE"):
        product_data_root("learning-capability", legacy_name=".legacy")
    monkeypatch.delenv("BUTLER_APP_DATA_DIR")
    with pytest.raises(AppDataPathError, match="NATIVE_APP_DATA_DIR_UNAVAILABLE"):
        product_data_root("learning-capability", legacy_name=".legacy")


def test_generation_state_rejects_duplicate_unknown_and_invalid_generation(
    tmp_path,
):
    path = tmp_path / "generation.json"
    invalid_payloads = (
        b'{"schema_version":1,"schema_version":1,"last_generation":1,'
        b'"last_snapshot_digest":"' + b"a" * 64 + b'"}',
        b'{"schema_version":1,"last_generation":true,'
        b'"last_snapshot_digest":"' + b"a" * 64 + b'"}',
        b'{"schema_version":1,"last_generation":-1,'
        b'"last_snapshot_digest":"' + b"a" * 64 + b'"}',
        b'{"schema_version":1,"last_generation":9007199254740992,'
        b'"last_snapshot_digest":"' + b"a" * 64 + b'"}',
        b'{"schema_version":1,"last_generation":1,'
        b'"last_snapshot_digest":"' + b"a" * 64 + b'","extra":1}',
    )
    for payload in invalid_payloads:
        _write_private(path, payload)
        with pytest.raises(GenerationStoreError):
            DurableGenerationStore(path).generation_for("b" * 64)


def test_atomic_write_failure_preserves_previous_valid_state(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "generation.json"
    store = DurableGenerationStore(path)
    assert store.generation_for("a" * 64) == 1
    original = path.read_bytes()

    import butler_pc_core.learning_capability.trusted_state as trusted_state

    def fail_replace(*_args, **_kwargs):
        raise OSError("injected")

    monkeypatch.setattr(trusted_state.os, "replace", fail_replace)
    with pytest.raises(GenerationStoreError):
        store.generation_for("b" * 64)
    assert path.read_bytes() == original


def test_final_reopen_identity_and_digest_mismatch_is_rejected(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "trusted" / "generation.json"
    store = DurableGenerationStore(path)
    assert store.generation_for("a" * 64) == 1

    import butler_pc_core.learning_capability.trusted_state as trusted_state

    original_replace = trusted_state.os.replace

    def replace_then_tamper(source, destination, **kwargs):
        original_replace(source, destination, **kwargs)
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_TRUNC,
            dir_fd=kwargs["dst_dir_fd"],
        )
        try:
            os.write(descriptor, b'{"tampered":true}')
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    monkeypatch.setattr(trusted_state.os, "replace", replace_then_tamper)
    with pytest.raises(GenerationStoreError):
        store.generation_for("b" * 64)


def test_non_posix_platform_fails_closed_without_generic_open(
    tmp_path,
    monkeypatch,
):
    import butler_pc_core.learning_capability.trusted_state as trusted_state

    state = TrustedStateFile(
        tmp_path / "trusted" / "state.json",
        max_file_bytes=128,
    )
    monkeypatch.setattr(trusted_state.os, "name", "nt")
    with pytest.raises(
        TrustedStateError,
        match="TRUST_STATE_PLATFORM_UNSUPPORTED",
    ):
        with state.locked():
            pass
