from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from butler_pc_core.fail_class import FailClass
from butler_pc_core.integrity.model_pack_verifier import ModelPackVerifier


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes = b"fixture") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(data)


def test_manifest_load_success(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema": "model_pack.v1"}), encoding="utf-8")
    parsed, result = ModelPackVerifier(tmp_path).load_manifest(manifest)
    assert parsed == {"schema": "model_pack.v1"}
    assert result.ok is True
    assert "manifest_sha" in result.details
    assert result.verified_at


def test_manifest_load_missing(tmp_path: Path):
    parsed, result = ModelPackVerifier(tmp_path).load_manifest(tmp_path / "missing.json")
    assert parsed is None
    assert result.ok is False
    assert result.fail_class == FailClass.MODEL_PACK_MISSING
    assert "raw_file_content" not in result.details


def test_model_pack_sha_match(tmp_path: Path):
    expected = _write(tmp_path / "model.gguf", b"model")
    result = ModelPackVerifier(tmp_path).verify_file("model.gguf", expected, FailClass.MODEL_PACK_SHA_MISMATCH)
    assert result.ok is True
    assert result.details["actual_sha"] == expected


def test_model_pack_sha_mismatch(tmp_path: Path):
    _write(tmp_path / "model.gguf", b"model")
    result = ModelPackVerifier(tmp_path).verify_file("model.gguf", "0" * 64, FailClass.MODEL_PACK_SHA_MISMATCH)
    assert result.ok is False
    assert result.fail_class == FailClass.MODEL_PACK_SHA_MISMATCH
    assert "actual_sha" in result.details
    assert "file_size" in result.details


def test_adapter_sha_match(tmp_path: Path):
    expected = _write(tmp_path / "adapter.safetensors", b"adapter")
    result = ModelPackVerifier(tmp_path).verify_file("adapter.safetensors", expected, FailClass.ADAPTER_SHA_MISMATCH)
    assert result.ok is True


def test_adapter_sha_mismatch(tmp_path: Path):
    _write(tmp_path / "adapter.safetensors", b"adapter")
    result = ModelPackVerifier(tmp_path).verify_file("adapter.safetensors", "1" * 64, FailClass.ADAPTER_SHA_MISMATCH)
    assert result.ok is False
    assert result.fail_class == FailClass.ADAPTER_SHA_MISMATCH


def test_tokenizer_sha_match(tmp_path: Path):
    expected = _write(tmp_path / "tokenizer.json", b"tokenizer")
    result = ModelPackVerifier(tmp_path).verify_file("tokenizer.json", expected, FailClass.TOKENIZER_SHA_MISMATCH)
    assert result.ok is True


def test_verify_all_pass_fail(tmp_path: Path):
    model_sha = _write(tmp_path / "m.gguf", b"m")
    adapter_sha = _write(tmp_path / "a.bin", b"a")
    tokenizer_sha = _write(tmp_path / "t.json", b"t")
    verifier = ModelPackVerifier(tmp_path)
    ok = verifier.verify_all({
        "model_path": "m.gguf",
        "model_sha256": model_sha,
        "adapter_path": "a.bin",
        "adapter_sha256": adapter_sha,
        "tokenizer_path": "t.json",
        "tokenizer_sha256": tokenizer_sha,
    })
    assert ok.ok is True
    bad = verifier.verify_all({"model_path": "m.gguf", "model_sha256": "2" * 64})
    assert bad.ok is False
    assert bad.fail_class == FailClass.MODEL_PACK_SHA_MISMATCH


def test_manifest_path_traversal_blocked(tmp_path: Path):
    outside = tmp_path.parent / "outside.bin"
    outside.write_bytes(b"outside")
    result = ModelPackVerifier(tmp_path).verify_file("../outside.bin", _sha(b"outside"), FailClass.MODEL_PACK_SHA_MISMATCH)
    assert result.ok is False
    assert result.fail_class == FailClass.SIGNATURE_INVALID
    assert "outside base_dir" in result.details["reason"]


def test_empty_manifest_fails_closed(tmp_path: Path):
    """
    Codex P1 회귀 방지 — 빈 manifest {} 본질은 ok=True 절대 0.
    이전 본질: path_key/sha_key 누락 시 continue → ok=True 통과 (fail-open).
    정정 본질: 즉시 fail-closed 반환.
    """
    result = ModelPackVerifier(tmp_path).verify_all({})
    assert result.ok is False
    assert result.fail_class == FailClass.MODEL_PACK_MISSING
    assert "missing_required_keys" in result.details["reason"]
    assert "model_path" in result.details["reason"]


def test_partial_manifest_fails_closed(tmp_path: Path):
    """
    Codex P1 회귀 방지 — 필수 키 일부 누락 본질도 ok=True 절대 0.
    path는 있으나 sha 누락 본질 (또는 그 역).
    """
    result = ModelPackVerifier(tmp_path).verify_all({"model_path": "model.bin"})
    assert result.ok is False
    assert result.fail_class == FailClass.MODEL_PACK_MISSING
    assert "model_sha256" in result.details["reason"]


def test_symlink_blocked_by_default(tmp_path: Path):
    target = tmp_path / "target.bin"
    target.write_bytes(b"target")
    link = tmp_path / "link.bin"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        return
    result = ModelPackVerifier(tmp_path).verify_file("link.bin", _sha(b"target"), FailClass.MODEL_PACK_SHA_MISMATCH)
    assert result.ok is False
    assert result.fail_class == FailClass.SIGNATURE_INVALID
    assert result.details["reason"] == "symlink blocked"


# ──────────────────────────────────────────────────────────────────────────────
# 신규 회귀 방지 — Codex P1 #6: load_manifest base_dir resolution
#
# 이전 본질: load_manifest이 manifest_path.parent를 manifest_dir 인자로 전달
#   → 상대 경로 manifest 본질이 process CWD 기준 resolve → in-scope manifest도
#   SIGNATURE_INVALID로 잘못 거부 (false fail-closed).
# 정정 본질: manifest_dir 인자 제거 → self.base_dir 기준 resolve (CWD 의존 0).
# 본 5건 테스트는 정정 본질 + 정책 본질 유지 모두 검증.
#
# FailClass 본질 정합: PR 본질 codebase에 PATH_TRAVERSAL enum 본질 0 → 기존
# "outside base_dir" 본질 처리에 사용되는 FailClass.SIGNATURE_INVALID 본질 사용.
# ──────────────────────────────────────────────────────────────────────────────

def test_relative_manifest_resolved_against_base_dir(tmp_path: Path, monkeypatch):
    """상대 경로 manifest 본질이 base_dir 기준 resolve (CWD 의존 0)."""
    base_dir = tmp_path / "verifier_root"
    base_dir.mkdir()
    manifest_file = base_dir / "manifest.json"
    manifest_file.write_text("{}", encoding="utf-8")

    # 의도적으로 다른 CWD 본질로 chdir — CWD 의존 본질이면 실패
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    verifier = ModelPackVerifier(base_dir=base_dir)
    parsed, result = verifier.load_manifest(Path("manifest.json"))

    # base_dir 내부 정합 manifest 본질 → SIGNATURE_INVALID 거부 본질 0
    assert result.fail_class != FailClass.SIGNATURE_INVALID, (
        f"상대 manifest 본질이 CWD 기준 resolve로 거부됨: {result.details}"
    )
    assert result.ok is True, f"정합 manifest 본질이 ok=True 아님: {result}"
    assert parsed == {}


def test_nested_relative_manifest_no_duplicate_segments(tmp_path: Path, monkeypatch):
    """nested 상대 경로 본질이 segment 중복 본질 0 (sub/manifest.json)."""
    base_dir = tmp_path / "verifier_root"
    sub_dir = base_dir / "sub"
    sub_dir.mkdir(parents=True)
    manifest_file = sub_dir / "manifest.json"
    manifest_file.write_text("{}", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    verifier = ModelPackVerifier(base_dir=base_dir)
    parsed, result = verifier.load_manifest(Path("sub/manifest.json"))

    assert result.fail_class != FailClass.SIGNATURE_INVALID, (
        f"nested 상대 manifest 본질 거부됨 (segment 중복 의심): {result.details}"
    )
    assert result.ok is True
    assert parsed == {}


def test_absolute_manifest_path_unchanged(tmp_path: Path):
    """절대 경로 manifest 본질은 그대로 사용 — base_dir 본질 join 0 (caller 호환)."""
    base_dir = tmp_path / "verifier_root"
    base_dir.mkdir()
    manifest_file = base_dir / "manifest.json"
    manifest_file.write_text("{}", encoding="utf-8")

    verifier = ModelPackVerifier(base_dir=base_dir)
    parsed, result = verifier.load_manifest(manifest_file)  # 절대 경로 전달

    assert result.fail_class != FailClass.SIGNATURE_INVALID
    assert result.ok is True
    assert parsed == {}


def test_manifest_outside_base_dir_rejected(tmp_path: Path):
    """
    base_dir 본질 외부 manifest 본질은 거부 (fail-closed 정책 유지).
    정정 본질이 정책 약화 0임을 보장.
    """
    base_dir = tmp_path / "verifier_root"
    base_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_manifest = outside / "manifest.json"
    outside_manifest.write_text("{}", encoding="utf-8")

    verifier = ModelPackVerifier(base_dir=base_dir)
    parsed, result = verifier.load_manifest(outside_manifest)

    assert result.ok is False
    assert result.fail_class == FailClass.SIGNATURE_INVALID, (
        f"외부 manifest 본질이 거부되지 0: {result}"
    )
    assert "outside base_dir" in result.details["reason"]
    assert parsed is None


def test_relative_manifest_resolved_independent_of_cwd(tmp_path: Path, monkeypatch):
    """동일 상대 경로 본질이 CWD 본질에 무관하게 동일 base_dir 본질로 resolve."""
    base_dir = tmp_path / "verifier_root"
    base_dir.mkdir()
    (base_dir / "manifest.json").write_text("{}", encoding="utf-8")

    verifier = ModelPackVerifier(base_dir=base_dir)

    # CWD #1
    monkeypatch.chdir(tmp_path)
    parsed1, result1 = verifier.load_manifest(Path("manifest.json"))

    # CWD #2
    cwd2 = tmp_path / "another"
    cwd2.mkdir()
    monkeypatch.chdir(cwd2)
    parsed2, result2 = verifier.load_manifest(Path("manifest.json"))

    # 두 본질 모두 정합 manifest 본질 (CWD 본질 독립)
    assert result1.fail_class != FailClass.SIGNATURE_INVALID
    assert result2.fail_class != FailClass.SIGNATURE_INVALID
    assert result1.ok is True
    assert result2.ok is True
    assert parsed1 == parsed2 == {}
