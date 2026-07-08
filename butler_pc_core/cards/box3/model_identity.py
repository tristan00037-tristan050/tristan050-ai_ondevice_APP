from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .human_approval_sealed import display_sha256_digest

BOX3_MODEL_PATH_ENVS: Final[tuple[str, ...]] = (
    "BUTLER_BOX3_V9_Q4_MODEL_PATH",
    "BUTLER_MODEL_PATH",
)
DEVICE_ID_PATH_ENV: Final[str] = "BUTLER_DEVICE_ID_PATH"
DEFAULT_DEVICE_ID_PATH: Final[Path] = Path.home() / ".butler" / "device_id"
_DEVICE_ID_NAMESPACE: Final[str] = "butler.device.v1:"
_IDENTITY_CACHE: dict[str, "Box3ModelIdentity"] = {}


@dataclass(frozen=True)
class Box3ModelIdentity:
    model_role: str
    model_path_digest: str
    model_size_bytes: int
    model_mtime_ns: int
    model_cache_key: str


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return display_sha256_digest(h.hexdigest(), prefix=True)


def compute_box3_model_identity(model_path: str | os.PathLike[str]) -> Box3ModelIdentity:
    path = Path(model_path)
    st = path.stat()
    digest = _sha256_file(path)
    cache_key = hashlib.sha256(f"{st.st_size}:{st.st_mtime_ns}:{digest}".encode("utf-8")).hexdigest()
    return Box3ModelIdentity(
        model_role="box3_draft",
        model_path_digest=digest,
        model_size_bytes=st.st_size,
        model_mtime_ns=st.st_mtime_ns,
        model_cache_key=cache_key,
    )


def _select_model_path_from_env() -> str | None:
    for env_name in BOX3_MODEL_PATH_ENVS:
        value = os.environ.get(env_name)
        if value:
            return value
    return None


def get_box3_model_identity_from_runtime_cache(model_path: str | os.PathLike[str] | None = None) -> Box3ModelIdentity | None:
    selected = str(model_path or _select_model_path_from_env() or "")
    if not selected:
        return None
    path = Path(selected)
    try:
        st = path.stat()
    except OSError:
        return None
    cache_key = str(path.resolve())
    cached = _IDENTITY_CACHE.get(cache_key)
    if cached and cached.model_size_bytes == st.st_size and cached.model_mtime_ns == st.st_mtime_ns:
        return cached
    try:
        identity = compute_box3_model_identity(path)
    except OSError:
        return None
    _IDENTITY_CACHE[cache_key] = identity
    return identity


def _device_id_path() -> Path:
    return Path(os.environ.get(DEVICE_ID_PATH_ENV, str(DEFAULT_DEVICE_ID_PATH)))


def _read_or_create_device_id(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raw = secrets.token_urlsafe(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(raw + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return raw


def get_runtime_device_id_digest(path: Path | None = None) -> str | None:
    selected = path or _device_id_path()
    try:
        raw = _read_or_create_device_id(selected)
    except OSError:
        return None
    digest = hashlib.sha256((_DEVICE_ID_NAMESPACE + raw).encode("utf-8")).hexdigest()
    return display_sha256_digest(digest, prefix=True)
