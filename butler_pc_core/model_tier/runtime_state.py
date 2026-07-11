from __future__ import annotations

import hashlib
import os
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


def sha256_file(path: Path, *, chunk_bytes: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class RuntimeStateMonitor:
    """Hashes model assets off the request thread and publishes immutable snapshots."""

    def __init__(self, provider: RuntimeProbeProvider, *, interval_seconds: float = 60.0) -> None:
        self._provider = provider
        self._interval_seconds = max(5.0, float(interval_seconds))
        self._states: dict[str, RuntimeVariantState] = {}
        self._file_cache: dict[str, tuple[int, int, str]] = {}
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
                    stat_result = path.stat()
                    is_file = path.is_file() and not path.is_symlink()
                    if is_file:
                        cache_key = str(path)
                        fingerprint = (stat_result.st_size, stat_result.st_mtime_ns)
                        cached = self._file_cache.get(cache_key)
                        if cached and cached[:2] == fingerprint:
                            model_digest = cached[2]
                        else:
                            model_digest = sha256_file(path)
                            self._file_cache[cache_key] = (*fingerprint, model_digest)
                except OSError:
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

    return (
        RuntimeProbe(
            variant_id=MAIN_4B_VARIANT_ID,
            model_path=os.environ.get("BUTLER_MODEL_PATH"),
            loaded=False,
            ready=False,
            process_id=os.getpid(),
        ),
        RuntimeProbe(
            variant_id=BOX3_1P7B_VARIANT_ID,
            model_path=os.environ.get("BUTLER_BOX3_V9_Q4_MODEL_PATH"),
            loaded=False,
            ready=bool(os.environ.get("BUTLER_BOX3_V9_Q4_MODEL_PATH")),
            process_id=os.getpid(),
        ),
    )
