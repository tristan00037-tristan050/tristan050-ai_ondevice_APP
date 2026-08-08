"""§4 잠금 로더 + §7 잠금 검증기 시험 (§11)."""
from __future__ import annotations

import json
import subprocess

import pytest
from ac25 import lock_verifier as lv


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True).stdout.decode().strip()


@pytest.fixture()
def fixture(tmp_path):
    """base→head 저장소 + 그에 맞는 유효 잠금 파일 경로를 만든다."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "src").mkdir()
    (repo / "src" / "a.ts").write_text("1\n")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    base_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    (repo / "src" / "a.ts").write_text("2\n")
    (repo / "src" / "b.ts").write_text("new\n")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "head")
    head = _git(repo, "rev-parse", "HEAD")
    head_tree = _git(repo, "rev-parse", "HEAD^{tree}")

    lock = {
        "schema_version": "butler.ac25.candidate_lock.v1",
        "repository": "github.com/x/y", "pr_number": 903,
        "approved_base_commit": base, "approved_base_tree": base_tree,
        "approved_head_commit": head, "approved_head_tree": head_tree,
        "allowed_paths": ["src/a.ts", "src/b.ts"],
        "identity_manifest_sha256": "b" * 64,
        "identity_artifact_zip_sha256": "5" * 64,
        "created_at": "2026-08-05T00:00:00Z", "expires_at": "2030-01-01T00:00:00Z",
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock))
    return {"repo": str(repo), "lock_path": str(lock_path), "lock": lock,
            "base": base, "base_tree": base_tree, "head": head, "head_tree": head_tree,
            "lock_dict": lock, "tmp": tmp_path}


def _write(fx, **over):
    d = dict(fx["lock_dict"]); d.update(over)
    p = fx["tmp"] / "lock2.json"; p.write_text(json.dumps(d)); return str(p)


def _codes(verdict):
    return {f.code for f in verdict.failures}


# ── expected head/tree 필수(§3, §11) ──────────────────────────────────
def test_expected_head_is_required(fixture):
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=fixture["lock_path"],
        expected_head="", expected_tree=fixture["head_tree"], execution_commit=fixture["head"])
    assert lv.LOCK_EXPECTED_HEAD_REQUIRED in _codes(v) and not v.ok


def test_blank_expected_head_is_rejected(fixture):
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=fixture["lock_path"],
        expected_head="   ".strip(), expected_tree=fixture["head_tree"], execution_commit=fixture["head"])
    assert lv.LOCK_EXPECTED_HEAD_REQUIRED in _codes(v)


def test_expected_tree_is_required(fixture):
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=fixture["lock_path"],
        expected_head=fixture["head"], expected_tree="", execution_commit=fixture["head"])
    assert lv.LOCK_EXPECTED_TREE_REQUIRED in _codes(v)


def test_valid_lock_passes(fixture):
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=fixture["lock_path"],
        expected_head=fixture["head"], expected_tree=fixture["head_tree"],
        execution_commit=fixture["head"])
    assert v.ok, _codes(v)
    assert set(v.changed_paths) == {"src/a.ts", "src/b.ts"}


def test_candidate_head_mismatch_is_rejected(fixture):
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=fixture["lock_path"],
        expected_head="0" * 40, expected_tree=fixture["head_tree"], execution_commit=fixture["head"])
    assert lv.LOCK_HEAD_MISMATCH in _codes(v)


def test_candidate_tree_mismatch_is_rejected(fixture):
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=fixture["lock_path"],
        expected_head=fixture["head"], expected_tree="0" * 40, execution_commit=fixture["head"])
    assert lv.LOCK_TREE_MISMATCH in _codes(v)


def test_scope_is_derived_from_lock(fixture):
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=fixture["lock_path"],
        expected_head=fixture["head"], expected_tree=fixture["head_tree"], execution_commit=fixture["head"])
    assert v.scope_start == fixture["base"] and v.scope_end == fixture["head"]


def test_base_tree_mismatch_is_rejected(fixture):
    p = _write(fixture, approved_base_tree="1" * 40)
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=p,
        expected_head=fixture["head"], expected_tree=fixture["head_tree"], execution_commit=fixture["head"])
    assert lv.LOCK_BASE_TREE_MISMATCH in _codes(v)


def test_head_tree_mismatch_in_lock_is_rejected(fixture):
    # 잠금이 주장한 head_tree 가 실제 git tree 와 다르면 닫힌다
    p = _write(fixture, approved_head_tree="2" * 40)
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=p,
        expected_head=fixture["head"], expected_tree="2" * 40, execution_commit=fixture["head"])
    assert lv.LOCK_HEAD_TREE_MISMATCH in _codes(v)


def test_git_object_not_found(fixture):
    p = _write(fixture, approved_base_commit="a" * 40)
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=p,
        expected_head=fixture["head"], expected_tree=fixture["head_tree"], execution_commit=fixture["head"])
    assert lv.GIT_OBJECT_NOT_FOUND in _codes(v)


def test_outside_allowlist_reports_offending(fixture):
    p = _write(fixture, allowed_paths=["src/a.ts"])  # src/b.ts 누락
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=p,
        expected_head=fixture["head"], expected_tree=fixture["head_tree"], execution_commit=fixture["head"])
    assert lv.CHANGED_PATH_OUTSIDE_ALLOWLIST in _codes(v)
    assert "src/b.ts" in v.offending_paths  # 정확한 경로 노출


def test_expired_lock_is_rejected(fixture, monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.setattr(lv, "_now", lambda: datetime(2099, 1, 1, tzinfo=timezone.utc))
    v = lv.verify_integration_lock(
        repository_path=fixture["repo"], lock_path=fixture["lock_path"],
        expected_head=fixture["head"], expected_tree=fixture["head_tree"], execution_commit=fixture["head"])
    assert lv.LOCK_EXPIRED in _codes(v)


# ── 엄격 로더(§4) ──────────────────────────────────────────────────────
def _base_lock():
    return {
        "schema_version": "butler.ac25.candidate_lock.v1",
        "repository": "r", "pr_number": 903,
        "approved_base_commit": "a" * 40, "approved_base_tree": "b" * 40,
        "approved_head_commit": "c" * 40, "approved_head_tree": "d" * 40,
        "allowed_paths": ["x/y.ts"],
        "identity_manifest_sha256": "e" * 64, "identity_artifact_zip_sha256": "f" * 64,
        "created_at": "2026-08-05T00:00:00Z", "expires_at": "2026-08-12T00:00:00Z",
    }


def test_unknown_lock_field_is_rejected():
    d = _base_lock(); d["surprise"] = 1
    with pytest.raises(lv.LockSchemaError) as e:
        lv.load_candidate_lock(json.dumps(d).encode())
    assert e.value.code == lv.LOCK_SCHEMA_INVALID


def test_missing_field_is_rejected():
    d = _base_lock(); del d["pr_number"]
    with pytest.raises(lv.LockSchemaError):
        lv.load_candidate_lock(json.dumps(d).encode())


def test_duplicate_json_key_is_rejected():
    raw = '{"schema_version":"butler.ac25.candidate_lock.v1","pr_number":903,"pr_number":904}'
    with pytest.raises(lv.LockSchemaError) as e:
        lv.load_candidate_lock(raw.encode())
    assert e.value.code == lv.LOCK_DUPLICATE_KEY


@pytest.mark.parametrize("field,val", [
    ("approved_base_commit", "XYZ"), ("approved_head_tree", "abc"),
    ("identity_manifest_sha256", "a" * 63), ("approved_base_commit", "A" * 40),
])
def test_malformed_oid_or_sha_is_rejected(field, val):
    d = _base_lock(); d[field] = val
    with pytest.raises(lv.LockSchemaError):
        lv.load_candidate_lock(json.dumps(d).encode())


@pytest.mark.parametrize("bad", ["/abs/p", "a\\b", "a/../b", ""])
def test_bad_allowed_path_is_rejected(bad):
    d = _base_lock(); d["allowed_paths"] = [bad]
    with pytest.raises(lv.LockSchemaError):
        lv.load_candidate_lock(json.dumps(d).encode())


def test_duplicate_allowed_path_is_rejected():
    d = _base_lock(); d["allowed_paths"] = ["x/y.ts", "x/y.ts"]
    with pytest.raises(lv.LockSchemaError):
        lv.load_candidate_lock(json.dumps(d).encode())


def test_case_only_conflict_path_is_rejected():
    d = _base_lock(); d["allowed_paths"] = ["x/Y.ts", "x/y.ts"]
    with pytest.raises(lv.LockSchemaError):
        lv.load_candidate_lock(json.dumps(d).encode())


def test_non_utc_time_is_rejected():
    d = _base_lock(); d["created_at"] = "2026-08-05T00:00:00+09:00"
    with pytest.raises(lv.LockSchemaError):
        lv.load_candidate_lock(json.dumps(d).encode())


def test_created_after_expires_is_rejected():
    d = _base_lock(); d["created_at"] = "2026-08-13T00:00:00Z"
    with pytest.raises(lv.LockSchemaError):
        lv.load_candidate_lock(json.dumps(d).encode())
