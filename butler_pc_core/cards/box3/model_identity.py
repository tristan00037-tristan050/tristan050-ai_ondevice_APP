"""Box3 model-scope approval — TOCTOU-hardened model identity & device digest (v1.2).

보완팀4(온디바이스) 계약:
- 승인 경로는 runtime cache 를 신뢰하지 않고 매번 물리 파일 full rehash 한다.
- 해싱은 fd 기반(open/fstat/read/fstat) + path stat 재확인으로 TOCTOU 를 줄인다.
- symlink 모델 경로는 거부한다(O_NOFOLLOW / lstat).
- identity 는 sha256 뿐 아니라 st_dev/st_ino/st_size/st_mtime_ns 와 realpath digest 를 포함한다.
- device digest 는 검증 경로에서 절대 생성하지 않는다(read-only). 생성은 프로비저닝 전용.
- 원문/절대경로/사용자명은 어떤 반환·로그에도 담지 않는다(digest-only).
"""
from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .actual_contracts import canonical_sha256, is_canonical_sha256
from .actual_fail_class import (
    APPROVED_MODEL_RUNTIME_MISMATCH,
    DEVICE_DIGEST_INVALID,
    MODEL_DIGEST_UNAVAILABLE,
    MODEL_FILE_CHANGED_DURING_HASH,
    MODEL_PATH_SWAPPED_AFTER_HASH,
    MODEL_PATH_SYMLINK_DENIED,
    Box3SecurityError,
)

BOX3_MODEL_PATH_ENV = "BUTLER_BOX3_V9_Q4_MODEL_PATH"
DEVICE_DIGEST_PATH_ENV = "BUTLER_BOX3_DEVICE_DIGEST_PATH"

_READ_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Box3ModelIdentity:
    model_digest: str
    model_path_digest: str
    realpath_digest: str
    size_bytes: int
    mtime_ns: int
    inode: int | None
    device: int | None

    def to_public_dict(self) -> dict[str, object]:
        """감사/로그용 digest-only 표현(원문 경로 0)."""
        return {
            "model_digest": self.model_digest,
            "model_path_digest": self.model_path_digest,
            "realpath_digest": self.realpath_digest,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
        }


def _env_model_path(environ: Mapping[str, str] | None) -> str | None:
    env = environ if environ is not None else os.environ
    return env.get(BOX3_MODEL_PATH_ENV)


def _digest_of_text(value: str) -> str:
    return canonical_sha256(hashlib.sha256(value.encode("utf-8")).hexdigest())


def hash_model_file_for_security(path: str) -> Box3ModelIdentity:
    """fd 기반 full rehash + TOCTOU 재확인. 실패는 고정 reason ValueError 로 raise.

    - lstat 로 symlink 를 먼저 거부(MODEL_PATH_SYMLINK_DENIED).
    - O_NOFOLLOW 가 있으면 open 단계에서도 symlink 를 거부한다.
    - 해싱 전/후 fstat 이 다르면 MODEL_FILE_CHANGED_DURING_HASH.
    - 해싱 후 path stat 이 fd stat 과 다르면(inode/dev/size/mtime) MODEL_PATH_SWAPPED_AFTER_HASH.
    """
    p = Path(path)
    lst = p.lstat()
    if stat.S_ISLNK(lst.st_mode):
        raise ValueError(MODEL_PATH_SYMLINK_DENIED)

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(p), flags)
    except OSError as exc:
        # O_NOFOLLOW 로 symlink 를 열려 하면 ELOOP → symlink deny 로 정규화.
        if getattr(exc, "errno", None) in (getattr(os, "ELOOP", None),):
            raise ValueError(MODEL_PATH_SYMLINK_DENIED) from exc
        raise
    try:
        st_before = os.fstat(fd)
        if stat.S_ISLNK(st_before.st_mode):
            raise ValueError(MODEL_PATH_SYMLINK_DENIED)
        h = hashlib.sha256()
        while True:
            chunk = os.read(fd, _READ_CHUNK)
            if not chunk:
                break
            h.update(chunk)
        st_after = os.fstat(fd)
    finally:
        os.close(fd)

    if (st_before.st_dev, st_before.st_ino, st_before.st_size, st_before.st_mtime_ns) != (
        st_after.st_dev,
        st_after.st_ino,
        st_after.st_size,
        st_after.st_mtime_ns,
    ):
        raise ValueError(MODEL_FILE_CHANGED_DURING_HASH)

    path_after = p.stat()
    if (path_after.st_dev, path_after.st_ino, path_after.st_size, path_after.st_mtime_ns) != (
        st_after.st_dev,
        st_after.st_ino,
        st_after.st_size,
        st_after.st_mtime_ns,
    ):
        raise ValueError(MODEL_PATH_SWAPPED_AFTER_HASH)

    return Box3ModelIdentity(
        model_digest=canonical_sha256(h.hexdigest()),
        model_path_digest=_digest_of_text(str(p)),
        realpath_digest=_digest_of_text(str(p.resolve(strict=True))),
        size_bytes=st_after.st_size,
        mtime_ns=st_after.st_mtime_ns,
        inode=getattr(st_after, "st_ino", None),
        device=getattr(st_after, "st_dev", None),
    )


def get_box3_model_identity_for_approval(
    model_path: str | None = None, *, environ: Mapping[str, str] | None = None
) -> Box3ModelIdentity | None:
    """승인 전용 identity — cache 미사용, 매번 full rehash. 실패는 None(fail-closed).

    반환 None 은 downstream 에서 MODEL_DIGEST_UNAVAILABLE 로 차단된다. 구체 reason 이 필요한
    스크립트/테스트는 hash_model_file_for_security 를 직접 호출한다.
    """
    env = environ if environ is not None else os.environ
    selected = str(model_path or "").strip()
    if not selected and os.environ.get("PYTEST_CURRENT_TEST"):
        selected = str(env.get(BOX3_MODEL_PATH_ENV) or "").strip()
    if not selected:
        try:
            from butler_pc_core.assets import get_asset_service
            from butler_pc_core.assets.context import get_platform_context

            context = get_platform_context()
            if context.manifest_set_sha256 is None:
                return None
            with get_asset_service().acquire(
                role="box3.model",
                purpose="box3-model-scope-approval",
                expected_manifest_set=context.manifest_set_sha256,
                request_id=str(uuid.uuid4()),
            ) as lease:
                asset = lease.require("model_gguf")
                return Box3ModelIdentity(
                    model_digest=canonical_sha256(asset.snapshot_digest),
                    model_path_digest=_digest_of_text("asset-authority:box3.model"),
                    realpath_digest=_digest_of_text("sealed-snapshot:box3.model"),
                    size_bytes=asset.entry.size_bytes,
                    mtime_ns=asset.identity.mtime_ns,
                    inode=None,
                    device=None,
                )
        except Exception:
            return None
    try:
        return hash_model_file_for_security(selected)
    except (OSError, ValueError):
        return None


def assert_runtime_model_identity_matches_approval(
    approved_identity: Box3ModelIdentity | None,
    *,
    runtime: object | None = None,
    model_path: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> None:
    """실제 생성 직전, 승인된 model identity 와 런타임 모델을 재대조한다.

    런타임이 loaded_model_sha256 을 노출하면 그 값을 우선 비교하고, 노출하지 않으면
    model_path(런타임/인자/env)를 다시 rehash 하여 비교한다. 불일치는 고정 reason 으로 raise.
    """
    if approved_identity is None:
        raise Box3SecurityError(MODEL_DIGEST_UNAVAILABLE)

    loaded_digest = getattr(runtime, "loaded_model_sha256", None) if runtime is not None else None
    if loaded_digest:
        try:
            normalized = canonical_sha256(loaded_digest)
        except ValueError as exc:
            raise Box3SecurityError(APPROVED_MODEL_RUNTIME_MISMATCH) from exc
        if normalized != approved_identity.model_digest:
            raise Box3SecurityError(APPROVED_MODEL_RUNTIME_MISMATCH)
        return

    runtime_path = getattr(runtime, "model_path", None) if runtime is not None else None
    current = get_box3_model_identity_for_approval(model_path or runtime_path, environ=environ)
    if current is None or current.model_digest != approved_identity.model_digest:
        raise Box3SecurityError(APPROVED_MODEL_RUNTIME_MISMATCH)


# ── device digest read/create 분리 ───────────────────────────────────────────
def default_device_digest_path(environ: Mapping[str, str] | None = None) -> Path:
    env = environ if environ is not None else os.environ
    override = env.get(DEVICE_DIGEST_PATH_ENV)
    if override:
        return Path(override)
    return Path.home() / ".butler" / "box3" / "runtime_device_id_digest"


def write_file_atomic_0600(path: Path, content: str) -> None:
    """temp(0600) → write → fsync → os.replace → chmod 0600 순 atomic write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".part")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, str(path))
        os.chmod(str(path), 0o600)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_runtime_device_id_digest(path: Path | None = None, *, environ: Mapping[str, str] | None = None) -> str | None:
    """검증 경로 전용 read-only. 파일이 없으면 생성하지 않고 None. 비정규형도 None."""
    p = path or default_device_digest_path(environ)
    try:
        raw = p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if not is_canonical_sha256(raw):
        return None
    return canonical_sha256(raw)


def ensure_runtime_device_id_digest(path: Path | None = None, *, environ: Mapping[str, str] | None = None) -> str:
    """프로비저닝 전용 — 대표 승인 파일 생성 스크립트에서만 호출한다.

    이미 존재하면 검증만(잘못되면 DEVICE_DIGEST_INVALID), 없으면 os.urandom 기반 digest 를
    0600 atomic 으로 생성한다. 검증 경로에서는 절대 호출하지 않는다.
    """
    p = path or default_device_digest_path(environ)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        digest = read_runtime_device_id_digest(p)
        if not digest:
            raise Box3SecurityError(DEVICE_DIGEST_INVALID)
        return digest
    secret = os.urandom(32)
    digest = canonical_sha256(hashlib.sha256(secret).hexdigest())
    write_file_atomic_0600(p, digest + "\n")
    return digest
