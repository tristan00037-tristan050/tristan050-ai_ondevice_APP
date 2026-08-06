"""§5 C1 — 외부 process 공개 출력 격리.

CLI 가 두 줄만 출력해도 자식 process 가 부모 stdout·stderr 를 상속하면 traceback·
절대경로·토큰 주변 문맥이 Actions log 로 직접 샌다. 공개 저장소이므로 log 는 누구나
본다. artifact 도 저장소 read 권한이면 누구나 받으므로 raw 를 첨부물로 올리는 것
역시 유출이다 — 창문을 막고 문을 새로 다는 일이다.

★이 모듈이 유일한 process 실행 지점이다. 다른 production 모듈은 subprocess·
  os.system·os.popen·asyncio.create_subprocess_*·os.exec*·os.posix_spawn* 를
  import 하지도 호출하지도 않는다.

★상한은 사후 절단이 아니라 ★실행 중★ 강제한다. 받은 뒤 자르면 잘리기 전까지는
  이미 다 받은 것이고, 악의적 출력이 러너 디스크·메모리를 먼저 채운다.

★자식만 죽이고 손자를 남기지 않는다. start_new_session=True 로 새 세션을 열고
  종료는 ★프로세스 그룹★ 단위로 한다.

★argv 원문을 보관하지 않는다. canonical JSON 의 SHA-256 만 남긴다. 토큰·서명·
  원문은 argv 에 넣지 않고 env 또는 stdin 으로 전달한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

MAX_STDOUT_BYTES = 4 * 1024 * 1024
MAX_STDERR_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
TERMINATE_GRACE_SECONDS = 3
_READER_JOIN_SECONDS = 10
_CHUNK = 65536

CONTAINMENT_ARGV_INVALID = "CONTAINMENT_ARGV_INVALID"
CONTAINMENT_CWD_INVALID = "CONTAINMENT_CWD_INVALID"
CONTAINMENT_CAPTURE_ROOT_INVALID = "CONTAINMENT_CAPTURE_ROOT_INVALID"
CONTAINMENT_SPAWN_FAILED = "CONTAINMENT_SPAWN_FAILED"
CONTAINMENT_CAPTURE_FAILED = "CONTAINMENT_CAPTURE_FAILED"
CONTAINMENT_TIMEOUT = "CONTAINMENT_TIMEOUT"
CONTAINMENT_OUTPUT_TOO_LARGE = "CONTAINMENT_OUTPUT_TOO_LARGE"
CONTAINMENT_PROCESS_GROUP_CLEANUP_FAILED = "CONTAINMENT_PROCESS_GROUP_CLEANUP_FAILED"

_FORBIDDEN_ARGV_CHARS = ("\x00", "\r", "\n")


@dataclass(frozen=True)
class ContainedResult:
    returncode: int
    argv_sha256: str
    stdout_sha256: str
    stderr_sha256: str
    stdout_bytes_observed: int
    stderr_bytes_observed: int
    stdout_bytes_retained: int
    stderr_bytes_retained: int
    truncated: bool
    stdout_path: Path
    stderr_path: Path

    def as_receipt(self) -> dict:
        """§5-6 이 허용한 metadata 만. raw 는 어디에도 넣지 않는다."""
        return {
            "argv_sha256": self.argv_sha256,
            "returncode": self.returncode,
            "stdout_sha256": self.stdout_sha256,
            "stderr_sha256": self.stderr_sha256,
            "stdout_bytes_observed": self.stdout_bytes_observed,
            "stderr_bytes_observed": self.stderr_bytes_observed,
            "truncated": self.truncated,
        }


class ContainmentError(RuntimeError):
    """★메시지에 error code 외 어떤 raw 값·경로도 넣지 않는다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def argv_digest(argv: Sequence[str]) -> str:
    canonical = json.dumps(list(argv), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_argv(argv: Sequence[str]) -> list[str]:
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
        raise ContainmentError(CONTAINMENT_ARGV_INVALID)
    items = list(argv)
    if not items:
        raise ContainmentError(CONTAINMENT_ARGV_INVALID)
    for item in items:
        if not isinstance(item, str) or not item:
            raise ContainmentError(CONTAINMENT_ARGV_INVALID)
        if any(bad in item for bad in _FORBIDDEN_ARGV_CHARS):
            raise ContainmentError(CONTAINMENT_ARGV_INVALID)
    return items


def _validate_directory(path: Path, code: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ContainmentError(code) from exc
    if not resolved.is_dir():
        raise ContainmentError(code)
    return resolved


class _StreamCapture:
    """한 stream 을 파일로 흘려 보내며 ★읽는 중에★ 상한을 센다."""

    def __init__(self, source, target: Path, limit: int) -> None:
        self.source = source
        self.target = target
        self.limit = limit
        self.observed = 0
        self.retained = 0
        self.overflowed = False
        self.failed = False
        self._digest = hashlib.sha256()
        self._thread = threading.Thread(target=self._drain, daemon=True)

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _drain(self) -> None:
        try:
            handle = os.open(str(self.target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(handle, "wb") as sink:
                while True:
                    chunk = self.source.read(_CHUNK)
                    if not chunk:
                        break
                    self.observed += len(chunk)
                    if self.observed > self.limit:
                        self.overflowed = True
                        break
                    self.retained += len(chunk)
                    self._digest.update(chunk)
                    sink.write(chunk)
        except OSError:
            self.failed = True
        finally:
            try:
                self.source.close()
            except OSError:
                pass


def _terminate_group(process: subprocess.Popen) -> bool:
    """★프로세스 그룹 전체를 종료한다. 자식만 죽이면 손자가 남는다."""
    try:
        group = os.getpgid(process.pid)
    except (OSError, ProcessLookupError):
        return True
    for sender, wait in ((signal.SIGTERM, TERMINATE_GRACE_SECONDS), (signal.SIGKILL, 5)):
        try:
            os.killpg(group, sender)
        except (OSError, ProcessLookupError):
            pass
        try:
            process.wait(timeout=wait)
            break
        except subprocess.TimeoutExpired:
            continue
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        return False
    # 그룹에 남은 손자가 없는지 확인한다
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return True
    return False


def run_contained(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    runner_temp: Path,
    stdin_path: Path | None = None,
) -> ContainedResult:
    """외부 process 를 shell 없이 실행하고 두 stream 을 실행 중에 제한한다."""
    items = _validate_argv(argv)
    working = _validate_directory(cwd, CONTAINMENT_CWD_INVALID)
    capture_root = _validate_directory(runner_temp, CONTAINMENT_CAPTURE_ROOT_INVALID)

    try:
        capture_dir = Path(tempfile.mkdtemp(dir=str(capture_root), prefix="ac25-cap-"))
        os.chmod(capture_dir, 0o700)
    except OSError as exc:
        raise ContainmentError(CONTAINMENT_CAPTURE_ROOT_INVALID) from exc

    stdout_path = capture_dir / "stdout.bin"
    stderr_path = capture_dir / "stderr.bin"

    # ★부모 stdin 을 상속시키지 않는다. 파일이 지정되면 그 파일만 연다.
    stdin_handle = subprocess.DEVNULL
    stdin_stream = None
    if stdin_path is not None:
        try:
            stdin_stream = open(Path(stdin_path).resolve(strict=True), "rb")
        except OSError as exc:
            shutil.rmtree(capture_dir, ignore_errors=True)
            raise ContainmentError(CONTAINMENT_CAPTURE_FAILED) from exc
        stdin_handle = stdin_stream

    try:
        process = subprocess.Popen(  # noqa: S603 - argv 배열 · shell 없음
            items,
            cwd=str(working),
            env=dict(env),
            stdin=stdin_handle,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        shutil.rmtree(capture_dir, ignore_errors=True)
        raise ContainmentError(CONTAINMENT_SPAWN_FAILED) from exc
    finally:
        if stdin_stream is not None:
            stdin_stream.close()

    out = _StreamCapture(process.stdout, stdout_path, MAX_STDOUT_BYTES)
    err = _StreamCapture(process.stderr, stderr_path, MAX_STDERR_BYTES)
    out.start()
    err.start()

    timed_out = False
    overflowed = False
    cleanup_ok = True

    watchdog_stop = threading.Event()

    def _watch_total() -> None:
        nonlocal overflowed
        while not watchdog_stop.wait(0.05):
            if out.overflowed or err.overflowed or (out.observed + err.observed) > MAX_TOTAL_BYTES:
                overflowed = True
                _terminate_group(process)
                return

    watchdog = threading.Thread(target=_watch_total, daemon=True)
    watchdog.start()

    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        cleanup_ok = _terminate_group(process)
    finally:
        watchdog_stop.set()
        watchdog.join(timeout=2)

    if not out.join(_READER_JOIN_SECONDS) or not err.join(_READER_JOIN_SECONDS):
        cleanup_ok = False
    if out.overflowed or err.overflowed or (out.observed + err.observed) > MAX_TOTAL_BYTES:
        overflowed = True

    if out.failed or err.failed:
        shutil.rmtree(capture_dir, ignore_errors=True)
        raise ContainmentError(CONTAINMENT_CAPTURE_FAILED)
    if not cleanup_ok:
        shutil.rmtree(capture_dir, ignore_errors=True)
        raise ContainmentError(CONTAINMENT_PROCESS_GROUP_CLEANUP_FAILED)
    if overflowed:
        shutil.rmtree(capture_dir, ignore_errors=True)
        raise ContainmentError(CONTAINMENT_OUTPUT_TOO_LARGE)
    if timed_out:
        shutil.rmtree(capture_dir, ignore_errors=True)
        raise ContainmentError(CONTAINMENT_TIMEOUT)

    return ContainedResult(
        returncode=process.returncode if process.returncode is not None else -1,
        argv_sha256=argv_digest(items),
        stdout_sha256=out.sha256,
        stderr_sha256=err.sha256,
        stdout_bytes_observed=out.observed,
        stderr_bytes_observed=err.observed,
        stdout_bytes_retained=out.retained,
        stderr_bytes_retained=err.retained,
        truncated=False,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def read_capture(path: Path, *, limit: int) -> bytes:
    """capture 파일을 상한 안에서 읽는다. 호출부는 finally 로 지운다."""
    try:
        with open(path, "rb") as handle:
            return handle.read(limit)
    except OSError as exc:
        raise ContainmentError(CONTAINMENT_CAPTURE_FAILED) from exc


def discard(result: ContainedResult) -> None:
    """capture directory 를 지운다. 실패해도 raw 를 노출하지 않는다."""
    shutil.rmtree(result.stdout_path.parent, ignore_errors=True)


DEFAULT_TIMEOUT_SECONDS = 900
_PARSE_LIMIT = 4 * 1024 * 1024


def run_and_read(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner_temp: Path | None = None,
    stdout_limit: int = _PARSE_LIMIT,
    stderr_limit: int = _PARSE_LIMIT,
    stdin_path: Path | None = None,
) -> tuple[int, bytes, bytes]:
    """실행하고 ★같은 process 안에서★ capture 를 읽은 뒤 즉시 지운다.

    돌려주는 bytes 는 호출부가 strict parser 로 해석하기 위한 것이다.
    ★그 bytes 를 예외 메시지·receipt·로그에 넣으면 안 된다. 분류에만 쓴다.
    """
    result = run_contained(
        argv,
        cwd=cwd,
        env=dict(env if env is not None else os.environ),
        timeout_seconds=timeout_seconds,
        runner_temp=runner_temp or default_runner_temp(),
        stdin_path=stdin_path,
    )
    try:
        out = read_capture(result.stdout_path, limit=stdout_limit)
        err = read_capture(result.stderr_path, limit=stderr_limit)
    finally:
        discard(result)
    return result.returncode, out, err


def default_runner_temp() -> Path:
    runner_temp = os.environ.get("RUNNER_TEMP")
    return Path(runner_temp) if runner_temp else Path(tempfile.gettempdir())


__all__ = [
    "CONTAINMENT_ARGV_INVALID",
    "CONTAINMENT_CAPTURE_FAILED",
    "CONTAINMENT_CAPTURE_ROOT_INVALID",
    "CONTAINMENT_CWD_INVALID",
    "CONTAINMENT_OUTPUT_TOO_LARGE",
    "CONTAINMENT_PROCESS_GROUP_CLEANUP_FAILED",
    "CONTAINMENT_SPAWN_FAILED",
    "CONTAINMENT_TIMEOUT",
    "MAX_STDERR_BYTES",
    "MAX_STDOUT_BYTES",
    "MAX_TOTAL_BYTES",
    "TERMINATE_GRACE_SECONDS",
    "ContainedResult",
    "ContainmentError",
    "DEFAULT_TIMEOUT_SECONDS",
    "argv_digest",
    "default_runner_temp",
    "discard",
    "read_capture",
    "run_and_read",
    "run_contained",
]
