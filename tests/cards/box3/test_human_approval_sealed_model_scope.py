"""Box3 model-scope approval P0 TOCTOU 하드닝 단위 테스트 (v1.2 §7)."""
from __future__ import annotations

import os
import stat as stat_mod

import pytest

from butler_pc_core.cards.box3 import model_identity as MI
from butler_pc_core.cards.box3.actual_contracts import canonical_sha256
from butler_pc_core.cards.box3.actual_fail_class import Box3SecurityError, HumanApprovalError
from butler_pc_core.cards.box3.human_approval_sealed import (
    APPROVAL_CONTEXT_DESKTOP_APP,
    APPROVAL_CONTEXT_EVAL_PIPELINE,
    APPROVAL_MODE_MODEL,
    APPROVAL_MODE_REQUEST,
    evaluate_human_approval_sealed,
    resolve_expected_scope_digest,
)


def _model(tmp_path, content: bytes = b"BOX3" * 4096):
    p = tmp_path / "box3.gguf"
    p.write_bytes(content)
    return p


class _FakeStat:
    def __init__(self, real, **overrides):
        self.st_dev = real.st_dev
        self.st_ino = real.st_ino
        self.st_size = real.st_size
        self.st_mtime_ns = real.st_mtime_ns
        self.st_atime_ns = getattr(real, "st_atime_ns", 0)
        self.st_mode = real.st_mode
        for key, value in overrides.items():
            setattr(self, key, value)


# ── identity / TOCTOU ────────────────────────────────────────────────────────
def test_symlink_model_path_denied(tmp_path):
    model = _model(tmp_path)
    link = tmp_path / "link.gguf"
    link.symlink_to(model)
    with pytest.raises(ValueError) as exc:
        MI.hash_model_file_for_security(str(link))
    assert str(exc.value) == "MODEL_PATH_SYMLINK_DENIED"


def test_hash_detects_file_changed_during_hash(tmp_path, monkeypatch):
    model = _model(tmp_path)
    real_fstat = os.fstat
    calls = {"n": 0}

    def fake_fstat(fd):
        real = real_fstat(fd)
        calls["n"] += 1
        if calls["n"] >= 2:  # st_after 시점에 mtime 이 바뀐 것으로 위장
            return _FakeStat(real, st_mtime_ns=real.st_mtime_ns + 1)
        return _FakeStat(real)

    monkeypatch.setattr(os, "fstat", fake_fstat)
    with pytest.raises(ValueError) as exc:
        MI.hash_model_file_for_security(str(model))
    assert str(exc.value) == "MODEL_FILE_CHANGED_DURING_HASH"


def test_hash_detects_path_swapped_after_hash(tmp_path, monkeypatch):
    model = _model(tmp_path)
    real_fstat = os.fstat

    def fake_fstat(fd):
        real = real_fstat(fd)
        return _FakeStat(real, st_ino=real.st_ino + 1)  # fd inode 를 path inode 와 다르게 위장

    monkeypatch.setattr(os, "fstat", fake_fstat)
    with pytest.raises(ValueError) as exc:
        MI.hash_model_file_for_security(str(model))
    assert str(exc.value) == "MODEL_PATH_SWAPPED_AFTER_HASH"


def test_approval_path_never_uses_runtime_cache(tmp_path, monkeypatch):
    """승인 전용 identity 는 매번 full rehash — 동일 경로 내용 교체 시 digest 가 바뀐다."""
    model = _model(tmp_path, b"AAAA" * 4096)
    monkeypatch.setenv(MI.BOX3_MODEL_PATH_ENV, str(model))
    first = MI.get_box3_model_identity_for_approval()
    model.write_bytes(b"BBBB" * 4096)
    second = MI.get_box3_model_identity_for_approval()
    assert first is not None and second is not None
    assert first.model_digest != second.model_digest


def test_same_size_mtime_replacement_blocked(tmp_path, monkeypatch):
    """size/mtime 을 보존한 내용 교체도 model_digest 변화로 SCOPE_MISMATCH 를 만든다."""
    model = _model(tmp_path, b"AAAA" * 4096)
    monkeypatch.setenv(MI.BOX3_MODEL_PATH_ENV, str(model))
    approved = MI.get_box3_model_identity_for_approval()
    st = model.stat()
    swapped = b"BBBB" * 4096
    assert len(swapped) == st.st_size
    model.write_bytes(swapped)
    os.utime(model, ns=(st.st_atime_ns, st.st_mtime_ns))
    with pytest.raises(Box3SecurityError) as exc:
        MI.assert_runtime_model_identity_matches_approval(approved)
    assert str(exc.value) == "APPROVED_MODEL_RUNTIME_MISMATCH"


def test_actual_operation_rechecks_runtime_identity(tmp_path, monkeypatch):
    """런타임 loaded digest 가 승인 identity 와 다르면 재대조가 차단한다."""
    model = _model(tmp_path)
    monkeypatch.setenv(MI.BOX3_MODEL_PATH_ENV, str(model))
    approved = MI.get_box3_model_identity_for_approval()

    class RuntimeOk:
        loaded_model_sha256 = approved.model_digest

    class RuntimeBad:
        loaded_model_sha256 = canonical_sha256("0" * 64)

    MI.assert_runtime_model_identity_matches_approval(approved, runtime=RuntimeOk())
    with pytest.raises(Box3SecurityError):
        MI.assert_runtime_model_identity_matches_approval(approved, runtime=RuntimeBad())


# ── context / mode ───────────────────────────────────────────────────────────
def test_desktop_rejects_request_scope():
    with pytest.raises(HumanApprovalError) as exc:
        resolve_expected_scope_digest(
            {"approval_mode": APPROVAL_MODE_REQUEST},
            request_digest=canonical_sha256("a" * 64),
            model_digest=canonical_sha256("b" * 64),
            context=APPROVAL_CONTEXT_DESKTOP_APP,
        )
    assert str(exc.value) == "APP_MODEL_SCOPE_REQUIRED"


def test_eval_pipeline_request_scope_unchanged():
    digest, mode = resolve_expected_scope_digest(
        {},
        request_digest=canonical_sha256("a" * 64),
        model_digest=None,
        context=APPROVAL_CONTEXT_EVAL_PIPELINE,
    )
    assert mode == APPROVAL_MODE_REQUEST
    assert digest == canonical_sha256("a" * 64)


def test_verdict_to_dict_contains_mode_and_context():
    verdict = evaluate_human_approval_sealed(
        None,
        expected_scope_digest=canonical_sha256("a" * 64),
        approval_mode=APPROVAL_MODE_MODEL,
        approval_context=APPROVAL_CONTEXT_DESKTOP_APP,
    )
    data = verdict.to_dict()
    assert data["approval_mode"] == APPROVAL_MODE_MODEL
    assert data["approval_context"] == APPROVAL_CONTEXT_DESKTOP_APP


# ── device digest read/create 분리 ──────────────────────────────────────────
def test_device_read_missing_returns_none(tmp_path):
    target = tmp_path / "dev" / "digest"
    assert MI.read_runtime_device_id_digest(target) is None
    assert not target.exists()  # 검증 경로는 파일을 생성하지 않는다


def test_ensure_device_digest_creates_0600(tmp_path):
    target = tmp_path / "dev" / "digest"
    digest = MI.ensure_runtime_device_id_digest(target)
    assert digest.startswith("sha256:")
    assert stat_mod.S_IMODE(target.stat().st_mode) == 0o600
    assert MI.read_runtime_device_id_digest(target) == digest
