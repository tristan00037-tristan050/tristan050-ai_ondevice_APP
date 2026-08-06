"""§5 C1 · §4 R6-1 — 외부 process 공개 출력 격리 + 후손 완전 정리.

CLI 가 두 줄만 출력해도 자식 process 가 부모 stdout·stderr 를 상속하면 traceback·
절대경로·토큰 주변 문맥이 Actions log 로 직접 샌다. 공개 저장소이므로 log 는 누구나
본다. artifact 도 저장소 read 권한이면 누구나 받으므로 raw 를 첨부물로 올리는 것
역시 유출이다 — 창문을 막고 문을 새로 다는 일이다.

★이 모듈이 유일한 process 실행 지점이다. 다른 production 모듈은 subprocess·
  os.system·os.popen·asyncio.create_subprocess_*·os.exec*·os.posix_spawn* 를
  import 하지도 호출하지도 않는다.

★실행은 전부 linux_subreaper 의 전용 supervisor 프로세스를 거친다(R6-1).
  timeout·출력 초과 때만이 아니라 ★정상 종료 경로에서도★ 후손을 센다.
  `setsid()` 로 세션을 이탈한 후손도 supervisor(child-subreaper)에게
  재부모화되므로 잡힌다. PGID 검사 단독안은 완료 기준이 아니다(§4-1).

★상한은 사후 절단이 아니라 ★실행 중★ 강제한다. supervisor 가 파일 크기를
  감시하다 넘는 즉시 그룹을 종료한다.

★argv 원문을 보관하지 않는다. canonical JSON 의 SHA-256 만 남긴다. 토큰·서명·
  원문은 argv 에 넣지 않고 env 또는 stdin 으로 전달한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from . import linux_subreaper

MAX_STDOUT_BYTES = 4 * 1024 * 1024
MAX_STDERR_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024

CONTAINMENT_ARGV_INVALID = "CONTAINMENT_ARGV_INVALID"
CONTAINMENT_CWD_INVALID = "CONTAINMENT_CWD_INVALID"
CONTAINMENT_CAPTURE_ROOT_INVALID = "CONTAINMENT_CAPTURE_ROOT_INVALID"
CONTAINMENT_SPAWN_FAILED = "CONTAINMENT_SPAWN_FAILED"
CONTAINMENT_CAPTURE_FAILED = "CONTAINMENT_CAPTURE_FAILED"
CONTAINMENT_TIMEOUT = "CONTAINMENT_TIMEOUT"
CONTAINMENT_OUTPUT_TOO_LARGE = "CONTAINMENT_OUTPUT_TOO_LARGE"
CONTAINMENT_PROCESS_GROUP_CLEANUP_FAILED = "CONTAINMENT_PROCESS_GROUP_CLEANUP_FAILED"
# R6-1 신설 코드는 linux_subreaper 가 정의한다. 여기서 재노출한다.
CONTAINMENT_SUBREAPER_UNAVAILABLE = linux_subreaper.CONTAINMENT_SUBREAPER_UNAVAILABLE
CONTAINMENT_SUBREAPER_ENABLE_FAILED = linux_subreaper.CONTAINMENT_SUBREAPER_ENABLE_FAILED
CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR = linux_subreaper.CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR
CONTAINMENT_SUPERVISOR_DIED = linux_subreaper.CONTAINMENT_SUPERVISOR_DIED
CONTAINMENT_PROCESS_IDENTITY_UNPROVEN = linux_subreaper.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN
CONTAINMENT_DESCENDANT_SURVIVED_ROOT = linux_subreaper.CONTAINMENT_DESCENDANT_SURVIVED_ROOT
CONTAINMENT_DESCENDANT_TERM_FAILED = linux_subreaper.CONTAINMENT_DESCENDANT_TERM_FAILED
CONTAINMENT_DESCENDANT_KILL_FAILED = linux_subreaper.CONTAINMENT_DESCENDANT_KILL_FAILED
CONTAINMENT_DESCENDANT_REAP_FAILED = linux_subreaper.CONTAINMENT_DESCENDANT_REAP_FAILED
CONTAINMENT_PROCESS_GROUP_NOT_EMPTY = linux_subreaper.CONTAINMENT_PROCESS_GROUP_NOT_EMPTY
CONTAINMENT_RAW_DELETE_FAILED = linux_subreaper.CONTAINMENT_RAW_DELETE_FAILED

_FORBIDDEN_ARGV_CHARS = ("\x00", "\r", "\n")


@dataclass(frozen=True)
class ContainedResult:
    """§4-3 지정 필드 그대로. 값을 추측해 채우지 않는다 — supervisor 실측만 담는다."""

    returncode: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_bytes: int
    stderr_bytes: int
    timed_out: bool
    output_limit_exceeded: bool
    descendants_observed: int
    descendants_terminated: int
    descendants_reaped: int
    descendant_escape_detected: bool
    process_group_empty: bool
    supervisor_children_empty: bool
    raw_files_deleted: bool
    cleanup_ok: bool

    def as_receipt(self) -> dict:
        """허용된 metadata 만. raw 는 어디에도 넣지 않는다(§3-3)."""
        return {
            "returncode": self.returncode,
            "stdout_sha256": self.stdout_sha256,
            "stderr_sha256": self.stderr_sha256,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "descendants_observed": self.descendants_observed,
            "cleanup_ok": self.cleanup_ok,
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


# supervisor 오류 코드 → 그대로 올린다. 여기 없는 코드는 protocol error 로 닫는다.
_RAISABLE_CODES = frozenset({
    CONTAINMENT_SPAWN_FAILED,
    CONTAINMENT_OUTPUT_TOO_LARGE,
    CONTAINMENT_TIMEOUT,
    CONTAINMENT_DESCENDANT_SURVIVED_ROOT,
    CONTAINMENT_SUBREAPER_UNAVAILABLE,
    CONTAINMENT_SUBREAPER_ENABLE_FAILED,
    CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR,
    CONTAINMENT_PROCESS_IDENTITY_UNPROVEN,
    CONTAINMENT_DESCENDANT_TERM_FAILED,
    CONTAINMENT_DESCENDANT_KILL_FAILED,
    CONTAINMENT_DESCENDANT_REAP_FAILED,
    CONTAINMENT_PROCESS_GROUP_NOT_EMPTY,
    CONTAINMENT_RAW_DELETE_FAILED,
})


def _raise_for_report(report: linux_subreaper.SupervisorReport) -> None:
    if report.error_code == "NONE":
        if not report.cleanup_ok:
            raise ContainmentError(CONTAINMENT_PROCESS_GROUP_CLEANUP_FAILED)
        return
    if report.error_code in _RAISABLE_CODES:
        raise ContainmentError(report.error_code)
    raise ContainmentError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)


def _result_from(report: linux_subreaper.SupervisorReport, *, raw_files_deleted: bool) -> ContainedResult:
    return ContainedResult(
        returncode=report.returncode,
        stdout_sha256=report.stdout_sha256,
        stderr_sha256=report.stderr_sha256,
        stdout_bytes=report.stdout_bytes,
        stderr_bytes=report.stderr_bytes,
        timed_out=report.timed_out,
        output_limit_exceeded=report.output_limit_exceeded,
        descendants_observed=report.descendants_observed,
        descendants_terminated=report.descendants_terminated,
        descendants_reaped=report.descendants_reaped,
        descendant_escape_detected=report.descendant_escape_detected,
        process_group_empty=report.process_group_empty,
        supervisor_children_empty=report.supervisor_children_empty,
        raw_files_deleted=raw_files_deleted,
        cleanup_ok=report.cleanup_ok and raw_files_deleted,
    )


def _supervised(
    items: list[str],
    *,
    working: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    capture_root: Path,
    stdin_path: Path | None,
    delete_raw: bool,
) -> tuple[linux_subreaper.SupervisorReport, Path]:
    try:
        capture_dir = Path(tempfile.mkdtemp(dir=str(capture_root), prefix="ac25-cap-"))
        os.chmod(capture_dir, 0o700)
    except OSError as exc:
        raise ContainmentError(CONTAINMENT_CAPTURE_ROOT_INVALID) from exc

    resolved_stdin: Path | None = None
    if stdin_path is not None:
        try:
            resolved_stdin = Path(stdin_path).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            shutil.rmtree(capture_dir, ignore_errors=True)
            raise ContainmentError(CONTAINMENT_CAPTURE_FAILED) from exc

    try:
        report = linux_subreaper.supervise(
            items,
            cwd=working,
            env=dict(env),
            timeout_seconds=timeout_seconds,
            stdout_path=capture_dir / "stdout.bin",
            stderr_path=capture_dir / "stderr.bin",
            stdout_limit=MAX_STDOUT_BYTES,
            stderr_limit=MAX_STDERR_BYTES,
            total_limit=MAX_TOTAL_BYTES,
            stdin_path=resolved_stdin,
            delete_raw=delete_raw,
        )
    except linux_subreaper.SubreaperProtocolError as exc:
        shutil.rmtree(capture_dir, ignore_errors=True)
        raise ContainmentError(exc.code) from exc
    except Exception as exc:  # noqa: BLE001 - raw 를 노출하지 않는다
        shutil.rmtree(capture_dir, ignore_errors=True)
        raise ContainmentError(CONTAINMENT_SUPERVISOR_DIED) from exc
    return report, capture_dir


def run_contained(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    runner_temp: Path,
    stdin_path: Path | None = None,
) -> ContainedResult:
    """외부 process 를 supervisor 아래에서 실행한다. raw 는 반환 전에 지워진다.

    timeout·출력 초과·이탈 후손·정리 실패는 전부 ContainmentError 로 닫는다.
    """
    items = _validate_argv(argv)
    working = _validate_directory(cwd, CONTAINMENT_CWD_INVALID)
    capture_root = _validate_directory(runner_temp, CONTAINMENT_CAPTURE_ROOT_INVALID)

    report, capture_dir = _supervised(
        items, working=working, env=env, timeout_seconds=timeout_seconds,
        capture_root=capture_root, stdin_path=stdin_path, delete_raw=True,
    )
    shutil.rmtree(capture_dir, ignore_errors=True)
    _raise_for_report(report)
    return _result_from(report, raw_files_deleted=report.raw_files_deleted)


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
    items = _validate_argv(argv)
    working = _validate_directory(cwd, CONTAINMENT_CWD_INVALID)
    capture_root = _validate_directory(
        runner_temp or default_runner_temp(), CONTAINMENT_CAPTURE_ROOT_INVALID
    )

    report, capture_dir = _supervised(
        items, working=working,
        env=dict(env if env is not None else os.environ),
        timeout_seconds=timeout_seconds,
        capture_root=capture_root, stdin_path=stdin_path, delete_raw=False,
    )
    try:
        out = _read_bounded(capture_dir / "stdout.bin", stdout_limit)
        err = _read_bounded(capture_dir / "stderr.bin", stderr_limit)
    finally:
        shutil.rmtree(capture_dir, ignore_errors=True)
    _raise_for_report(report)
    return report.returncode, out, err


def run_and_capture(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    runner_temp: Path,
    stdout_limit: int = _PARSE_LIMIT,
) -> tuple[ContainedResult, bytes]:
    """실행 결과 ★와★ stdout bytes 를 함께 돌려준다.

    §7-4 는 계약 출력에서 "허용 목록 key 와 0/1 값만" 구조화하라고 정한다.
    그러려면 후손·정리 지표(ContainedResult)와 파싱용 bytes 가 둘 다 필요하다.

    ★돌려준 bytes 를 로그·예외·영수증에 넣으면 안 된다. strict parser 입력으로만
      쓴다. 구조화한 key 와 0/1 값만 밖으로 나간다.
    """
    items = _validate_argv(argv)
    working = _validate_directory(cwd, CONTAINMENT_CWD_INVALID)
    capture_root = _validate_directory(runner_temp, CONTAINMENT_CAPTURE_ROOT_INVALID)

    report, capture_dir = _supervised(
        items, working=working, env=env, timeout_seconds=timeout_seconds,
        capture_root=capture_root, stdin_path=None, delete_raw=False,
    )
    try:
        out = _read_bounded(capture_dir / "stdout.bin", stdout_limit)
    finally:
        shutil.rmtree(capture_dir, ignore_errors=True)
    # ★상한 초과·시간 초과·이탈 후손은 여기서 닫는다. 계약 실패(exit≠0)는 닫지
    #   않는다 — 호출부가 그 종료 코드와 구조화된 key 로 판정해야 하기 때문이다.
    if report.error_code != "NONE":
        _raise_for_report(report)
    return _result_from(report, raw_files_deleted=True), out


def _read_bounded(path: Path, limit: int) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read(limit)
    except OSError:
        return b""


def default_runner_temp() -> Path:
    runner_temp = os.environ.get("RUNNER_TEMP")
    return Path(runner_temp) if runner_temp else Path(tempfile.gettempdir())


__all__ = [
    "CONTAINMENT_ARGV_INVALID",
    "CONTAINMENT_CAPTURE_FAILED",
    "CONTAINMENT_CAPTURE_ROOT_INVALID",
    "CONTAINMENT_CWD_INVALID",
    "CONTAINMENT_DESCENDANT_KILL_FAILED",
    "CONTAINMENT_DESCENDANT_REAP_FAILED",
    "CONTAINMENT_DESCENDANT_SURVIVED_ROOT",
    "CONTAINMENT_DESCENDANT_TERM_FAILED",
    "CONTAINMENT_OUTPUT_TOO_LARGE",
    "CONTAINMENT_PROCESS_GROUP_CLEANUP_FAILED",
    "CONTAINMENT_PROCESS_GROUP_NOT_EMPTY",
    "CONTAINMENT_PROCESS_IDENTITY_UNPROVEN",
    "CONTAINMENT_RAW_DELETE_FAILED",
    "CONTAINMENT_SPAWN_FAILED",
    "CONTAINMENT_SUBREAPER_ENABLE_FAILED",
    "CONTAINMENT_SUBREAPER_UNAVAILABLE",
    "CONTAINMENT_SUPERVISOR_DIED",
    "CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR",
    "CONTAINMENT_TIMEOUT",
    "MAX_STDERR_BYTES",
    "MAX_STDOUT_BYTES",
    "MAX_TOTAL_BYTES",
    "ContainedResult",
    "ContainmentError",
    "DEFAULT_TIMEOUT_SECONDS",
    "argv_digest",
    "default_runner_temp",
    "run_and_capture",
    "run_and_read",
    "run_contained",
]
