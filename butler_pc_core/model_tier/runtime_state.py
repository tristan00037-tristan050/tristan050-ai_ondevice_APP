from __future__ import annotations

import hashlib
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .contracts import RuntimeVariantState, sha256_text


@dataclass(frozen=True)
class RuntimeProbe:
    variant_id: str
    model_path: str | None
    loaded: bool
    ready: bool
    process_id: int | None = None


RuntimeProbeProvider = Callable[[], Iterable[RuntimeProbe]]
FileFingerprint = tuple[int, int, int, int, int]


@dataclass(frozen=True)
class RuntimeLifecycleState:
    model_path: str | None
    loaded: bool
    ready: bool
    process_id: int | None


_LIFECYCLE_LOCK = threading.Lock()
_LIFECYCLE_STATES: dict[str, RuntimeLifecycleState] = {}


def publish_runtime_lifecycle(
    variant_id: str,
    *,
    model_path: str | None,
    loaded: bool,
    ready: bool,
    process_id: int | None = None,
) -> None:
    """Publish state only from the component that owns the live Llama object."""
    if not variant_id or (ready and not loaded):
        raise ValueError("RUNTIME_LIFECYCLE_INVALID")
    state = RuntimeLifecycleState(
        model_path=model_path,
        loaded=bool(loaded),
        ready=bool(ready),
        process_id=process_id,
    )
    with _LIFECYCLE_LOCK:
        _LIFECYCLE_STATES[variant_id] = state


def runtime_lifecycle_snapshot() -> dict[str, RuntimeLifecycleState]:
    with _LIFECYCLE_LOCK:
        return dict(_LIFECYCLE_STATES)


def _fingerprint(stat_result: os.stat_result) -> FileFingerprint:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
    )


def sha256_file_with_identity(
    path: Path,
    *,
    chunk_bytes: int = 4 * 1024 * 1024,
) -> tuple[str, FileFingerprint]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    digest = hashlib.sha256()
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("MODEL_ASSET_NOT_REGULAR")
        while True:
            chunk = os.read(fd, chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(fd)
        path_after = os.stat(path, follow_symlinks=False)
    finally:
        os.close(fd)
    before_fingerprint = _fingerprint(before)
    if before_fingerprint != _fingerprint(after) or before_fingerprint != _fingerprint(path_after):
        raise ValueError("MODEL_ASSET_IDENTITY_CHANGED_DURING_HASH")
    return "sha256:" + digest.hexdigest(), before_fingerprint


def sha256_file(path: Path, *, chunk_bytes: int = 4 * 1024 * 1024) -> str:
    digest, _ = sha256_file_with_identity(path, chunk_bytes=chunk_bytes)
    return digest


class RuntimeStateMonitor:
    """Hashes model assets off the request thread and publishes immutable snapshots."""

    def __init__(self, provider: RuntimeProbeProvider, *, interval_seconds: float = 60.0) -> None:
        self._provider = provider
        self._interval_seconds = max(5.0, float(interval_seconds))
        self._states: dict[str, RuntimeVariantState] = {}
        self._file_cache: dict[str, tuple[FileFingerprint, str]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="model-tier-runtime-state",
            daemon=True,
        )

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def snapshot(self) -> dict[str, RuntimeVariantState]:
        with self._lock:
            return dict(self._states)

    def sample_once(self) -> dict[str, RuntimeVariantState]:
        probes = tuple(self._provider())
        sampled: dict[str, RuntimeVariantState] = {}
        for probe in probes:
            path = Path(probe.model_path).expanduser() if probe.model_path else None
            model_digest: str | None = None
            model_path_digest = sha256_text(str(path)) if path else None
            is_file = False
            if path is not None:
                try:
                    stat_result = os.stat(path, follow_symlinks=False)
                    is_file = stat.S_ISREG(stat_result.st_mode)
                    if is_file:
                        cache_key = str(path)
                        fingerprint = _fingerprint(stat_result)
                        cached = self._file_cache.get(cache_key)
                        if cached and cached[0] == fingerprint:
                            model_digest = cached[1]
                        else:
                            model_digest, hashed_fingerprint = sha256_file_with_identity(path)
                            self._file_cache[cache_key] = (hashed_fingerprint, model_digest)
                except (OSError, ValueError):
                    is_file = False
            state = RuntimeVariantState(
                variant_id=probe.variant_id,
                loaded=bool(probe.loaded),
                ready=bool(probe.ready and is_file and model_digest),
                model_digest=model_digest,
                model_path_digest=model_path_digest,
                process_id_digest=(
                    sha256_text(str(probe.process_id))
                    if isinstance(probe.process_id, int) and not isinstance(probe.process_id, bool)
                    else None
                ),
                asset_available=bool(is_file and model_digest),
            )
            try:
                state.validate()
            except ValueError:
                state = RuntimeVariantState(
                    variant_id=probe.variant_id,
                    loaded=False,
                    ready=False,
                    model_digest=model_digest,
                    model_path_digest=model_path_digest,
                    process_id_digest=None,
                    asset_available=bool(is_file and model_digest),
                )
            sampled[probe.variant_id] = state
        with self._lock:
            self._states = sampled
        return dict(sampled)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.sample_once()
            except Exception:
                pass
            self._stop.wait(self._interval_seconds)


def default_runtime_probe_provider() -> tuple[RuntimeProbe, ...]:
    from .capability_registry import BOX3_1P7B_VARIANT_ID, MAIN_4B_VARIANT_ID

    lifecycle = runtime_lifecycle_snapshot()

    def probe(variant_id: str, path_env: str) -> RuntimeProbe:
        state = lifecycle.get(variant_id)
        return RuntimeProbe(
            variant_id=variant_id,
            model_path=(state.model_path if state else None) or os.environ.get(path_env),
            loaded=bool(state and state.loaded),
            ready=bool(state and state.ready),
            process_id=state.process_id if state else os.getpid(),
        )

    return (
        probe(MAIN_4B_VARIANT_ID, "BUTLER_MODEL_PATH"),
        probe(BOX3_1P7B_VARIANT_ID, "BUTLER_BOX3_V9_Q4_MODEL_PATH"),
    )
