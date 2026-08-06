"""§4 R6-1 — 전용 Linux child-subreaper 감독 프로세스.

PGID 검사만으로는 `setsid()` 로 세션을 이탈한 후손을 셀 수 없다. 그래서 명령
실행마다 ★전용 supervisor 프로세스★ 를 만들고, 그 supervisor 가
`prctl(PR_SET_CHILD_SUBREAPER, 1)` 로 자신을 subreaper 로 만든 뒤 target 을
실행한다. target 계보의 어떤 프로세스가 부모를 잃으면 — double-fork 든
`setsid()` 든 — init 이 아니라 ★이 supervisor 에게★ 재부모화되므로 셀 수 있다.

★메인 검증 프로세스 자체를 subreaper 로 만들지 않는다(§4-2). 명령마다 별도
  supervisor 하나다. supervisor 는 자신이 만든 target 계보만 다룬다.
★전체 /proc 를 이름으로 검색하지 않는다. pkill·killall 을 쓰지 않는다.
  열거 기준은 ppid(내 자식)·pgid(target 그룹) 뿐이다 — 계보 기준이지 이름이
  아니다. 무관한 프로세스는 건드리지 않는다.
★PID 재사용을 신호 전에 방어한다. pidfd 를 우선 쓰고, 없으면 starttime 을
  매 신호 직전 재검증한다. 둘 다 못 쓰면 CONTAINMENT_PROCESS_IDENTITY_UNPROVEN
  으로 닫는다(§4-2). 위험을 감수하지 않는다.
★부모↔supervisor 통신은 길이 제한 JSON ★한 건★ 씩이다(§4-4). 제어는 stdin
  으로, 보고는 stdout 으로 간다. stdout/stderr 원문·traceback·환경 전체는
  이 메시지에 넣지 않는다.
★zombie 는 살아 있는 프로세스로 세지 않는다. 다만 수거(reap) 실패는 실패다.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

# ── prctl 상수 (linux/prctl.h) ─────────────────────────────────────────
PR_SET_CHILD_SUBREAPER = 36
PR_GET_CHILD_SUBREAPER = 37

# ── 시간 계약 (§4-2 5·6항. monotonic 으로만 잰다 §10-1) ────────────────
GRACE_SECONDS = 0.5
TERM_WAIT_SECONDS = 2.0
KILL_WAIT_SECONDS = 2.0
_POLL_SECONDS = 0.02
_SUPERVISOR_EXTRA_BUDGET_SECONDS = 30.0

# ── 통신 계약 (§4-4) ───────────────────────────────────────────────────
MAX_MESSAGE_BYTES = 1024 * 1024

# ── 오류 코드 (§4-3) ───────────────────────────────────────────────────
CONTAINMENT_SUBREAPER_UNAVAILABLE = "CONTAINMENT_SUBREAPER_UNAVAILABLE"
CONTAINMENT_SUBREAPER_ENABLE_FAILED = "CONTAINMENT_SUBREAPER_ENABLE_FAILED"
CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR = "CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR"
CONTAINMENT_SUPERVISOR_DIED = "CONTAINMENT_SUPERVISOR_DIED"
CONTAINMENT_PROCESS_IDENTITY_UNPROVEN = "CONTAINMENT_PROCESS_IDENTITY_UNPROVEN"
CONTAINMENT_DESCENDANT_SURVIVED_ROOT = "CONTAINMENT_DESCENDANT_SURVIVED_ROOT"
CONTAINMENT_DESCENDANT_TERM_FAILED = "CONTAINMENT_DESCENDANT_TERM_FAILED"
CONTAINMENT_DESCENDANT_KILL_FAILED = "CONTAINMENT_DESCENDANT_KILL_FAILED"
CONTAINMENT_DESCENDANT_REAP_FAILED = "CONTAINMENT_DESCENDANT_REAP_FAILED"
CONTAINMENT_PROCESS_GROUP_NOT_EMPTY = "CONTAINMENT_PROCESS_GROUP_NOT_EMPTY"
CONTAINMENT_RAW_DELETE_FAILED = "CONTAINMENT_RAW_DELETE_FAILED"
# 실행·상한 코드는 output_containment 의 기존 코드와 값이 같아야 한다.
CONTAINMENT_SPAWN_FAILED = "CONTAINMENT_SPAWN_FAILED"
CONTAINMENT_TIMEOUT = "CONTAINMENT_TIMEOUT"
CONTAINMENT_OUTPUT_TOO_LARGE = "CONTAINMENT_OUTPUT_TOO_LARGE"

_NO_ERROR = "NONE"
_ERROR_CODE_ALLOWLIST = frozenset({
    _NO_ERROR,
    CONTAINMENT_SUBREAPER_UNAVAILABLE,
    CONTAINMENT_SUBREAPER_ENABLE_FAILED,
    CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR,
    CONTAINMENT_PROCESS_IDENTITY_UNPROVEN,
    CONTAINMENT_DESCENDANT_SURVIVED_ROOT,
    CONTAINMENT_DESCENDANT_TERM_FAILED,
    CONTAINMENT_DESCENDANT_KILL_FAILED,
    CONTAINMENT_DESCENDANT_REAP_FAILED,
    CONTAINMENT_PROCESS_GROUP_NOT_EMPTY,
    CONTAINMENT_RAW_DELETE_FAILED,
    CONTAINMENT_SPAWN_FAILED,
    CONTAINMENT_TIMEOUT,
    CONTAINMENT_OUTPUT_TOO_LARGE,
})

_SHA256_RE_LEN = 64
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

_CONTROL_KEYS = frozenset({
    "argv", "cwd", "env", "timeout_seconds", "stdout_path", "stderr_path",
    "stdout_limit", "stderr_limit", "total_limit", "stdin_path", "delete_raw",
})
_REPORT_KEYS = frozenset({
    "returncode", "stdout_sha256", "stderr_sha256", "stdout_bytes",
    "stderr_bytes", "timed_out", "output_limit_exceeded",
    "descendants_observed", "descendants_terminated", "descendants_reaped",
    "descendant_escape_detected", "process_group_empty",
    "supervisor_children_empty", "raw_files_deleted", "cleanup_ok",
    "error_code",
})


class SubreaperProtocolError(Exception):
    """통신 계약 위반. 메시지에 raw 값·경로를 넣지 않는다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SupervisorReport:
    """supervisor 가 보낸 한 건의 보고. §4-3 필드명과 일치한다."""

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
    error_code: str


# ══ 공용 strict JSON ═══════════════════════════════════════════════════
def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
        seen[key] = value
    return seen


def _parse_message(raw: bytes, *, required_keys: frozenset[str]) -> dict:
    """길이 제한 JSON 한 건을 strict 파싱한다(§4-4)."""
    if not raw or len(raw) > MAX_MESSAGE_BYTES:
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    try:
        message = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR) from exc
    if not isinstance(message, dict) or set(message) != required_keys:
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    return message


def _require_int(value: object, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    return value


def _require_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    return value


def _require_digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_RE_LEN
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    return value


def parse_report(raw: bytes) -> SupervisorReport:
    """보고 메시지를 검증해 구조로 바꾼다. 위반은 전부 protocol error 다."""
    message = _parse_message(raw, required_keys=_REPORT_KEYS)
    error_code = message["error_code"]
    if not isinstance(error_code, str) or error_code not in _ERROR_CODE_ALLOWLIST:
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    returncode = message["returncode"]
    if not isinstance(returncode, int) or isinstance(returncode, bool):
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    return SupervisorReport(
        returncode=returncode,
        stdout_sha256=_require_digest(message["stdout_sha256"]),
        stderr_sha256=_require_digest(message["stderr_sha256"]),
        stdout_bytes=_require_int(message["stdout_bytes"]),
        stderr_bytes=_require_int(message["stderr_bytes"]),
        timed_out=_require_bool(message["timed_out"]),
        output_limit_exceeded=_require_bool(message["output_limit_exceeded"]),
        descendants_observed=_require_int(message["descendants_observed"]),
        descendants_terminated=_require_int(message["descendants_terminated"]),
        descendants_reaped=_require_int(message["descendants_reaped"]),
        descendant_escape_detected=_require_bool(message["descendant_escape_detected"]),
        process_group_empty=_require_bool(message["process_group_empty"]),
        supervisor_children_empty=_require_bool(message["supervisor_children_empty"]),
        raw_files_deleted=_require_bool(message["raw_files_deleted"]),
        cleanup_ok=_require_bool(message["cleanup_ok"]),
        error_code=error_code,
    )


# ══ /proc 계보 열거 (이름 검색 아님 — ppid·pgid 기준) ═══════════════════
@dataclass(frozen=True)
class ProcStat:
    pid: int
    state: str
    ppid: int
    pgrp: int
    starttime: int


def read_proc_stat(pid: int) -> ProcStat | None:
    """/proc/<pid>/stat 한 줄을 파싱한다. 없으면 None(이미 종료)."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_bytes()
    except OSError:
        return None
    text = raw.decode("ascii", "replace")
    # comm 은 괄호 안에 공백·괄호가 올 수 있다. 마지막 ') ' 뒤가 나머지다.
    head, separator, rest = text.rpartition(") ")
    if not separator:
        return None
    fields = rest.split()
    if len(fields) < 20:
        return None
    try:
        return ProcStat(
            pid=pid,
            state=fields[0],
            ppid=int(fields[1]),
            pgrp=int(fields[2]),
            starttime=int(fields[19]),
        )
    except ValueError:
        return None


def _iter_proc_pids() -> list[int]:
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    return [int(name) for name in entries if name.isdigit()]


def _is_alive(stat: ProcStat | None) -> bool:
    """zombie(Z)·dead(X) 는 살아 있는 프로세스로 세지 않는다(§4-2 8항)."""
    return stat is not None and stat.state not in ("Z", "X")


def living_children_of(parent_pid: int) -> list[ProcStat]:
    """ppid 기준 열거 — 내 계보만. 이름으로 찾지 않는다."""
    found: list[ProcStat] = []
    for pid in _iter_proc_pids():
        stat = read_proc_stat(pid)
        if stat is not None and stat.ppid == parent_pid and _is_alive(stat):
            found.append(stat)
    return found


def living_group_members(pgid: int, *, exclude: frozenset[int] = frozenset()) -> list[ProcStat]:
    """pgid 기준 열거 — target 그룹만."""
    found: list[ProcStat] = []
    for pid in _iter_proc_pids():
        if pid in exclude:
            continue
        stat = read_proc_stat(pid)
        if stat is not None and stat.pgrp == pgid and _is_alive(stat):
            found.append(stat)
    return found


# ══ PID 재사용 방어 (§4-2 pidfd 우선, starttime 대안) ═══════════════════
class _PinnedProcess:
    """신호를 보내기 전에 같은 프로세스임을 증명하는 손잡이."""

    def __init__(self, pid: int, starttime: int, pidfd: int | None) -> None:
        self.pid = pid
        self.starttime = starttime
        self.pidfd = pidfd

    def close(self) -> None:
        if self.pidfd is not None:
            try:
                os.close(self.pidfd)
            except OSError:
                pass
            self.pidfd = None

    def signal(self, signum: int) -> bool:
        """신호를 보낸다. 정체가 확인되지 않으면 예외로 닫는다(fail-closed)."""
        if self.pidfd is not None:
            try:
                signal.pidfd_send_signal(self.pidfd, signum)
                return True
            except ProcessLookupError:
                return False  # 이미 종료 — 재사용 위험 없음(pidfd 는 그 프로세스에 고정)
            except OSError as exc:
                raise SubreaperProtocolError(CONTAINMENT_PROCESS_IDENTITY_UNPROVEN) from exc
        # starttime 대안: 매 신호 ★직전★ 재검증한다(§4-2)
        stat = read_proc_stat(self.pid)
        if stat is None:
            return False
        if stat.starttime != self.starttime:
            raise SubreaperProtocolError(CONTAINMENT_PROCESS_IDENTITY_UNPROVEN)
        try:
            os.kill(self.pid, signum)
            return True
        except ProcessLookupError:
            return False
        except OSError as exc:
            raise SubreaperProtocolError(CONTAINMENT_PROCESS_IDENTITY_UNPROVEN) from exc


def pin_process(pid: int, starttime: int) -> _PinnedProcess:
    """pidfd 를 우선 시도하고, 안 되면 starttime 모드로 내려간다.

    pidfd 도 starttime 도 확보할 수 없으면 정체 불명이다 — 예외로 닫는다.
    """
    pidfd: int | None = None
    opener = getattr(os, "pidfd_open", None)
    sender = getattr(signal, "pidfd_send_signal", None)
    if opener is not None and sender is not None:
        try:
            pidfd = opener(pid, 0)
        except OSError:
            pidfd = None
    if pidfd is None:
        stat = read_proc_stat(pid)
        if stat is None:
            # 이미 종료한 프로세스 — starttime 0 으로 고정하면 signal() 이 False 를 낸다
            return _PinnedProcess(pid, starttime, None)
        if stat.starttime != starttime:
            raise SubreaperProtocolError(CONTAINMENT_PROCESS_IDENTITY_UNPROVEN)
    return _PinnedProcess(pid, starttime, pidfd)


# ══ subreaper 설정 ═════════════════════════════════════════════════════
def enable_child_subreaper() -> str:
    """PR_SET_CHILD_SUBREAPER=1 을 걸고 PR_GET 으로 실제 1 을 재확인한다.

    성공하면 "" 를, 실패하면 해당 오류 코드를 돌려준다.
    """
    if sys.platform != "linux":
        return CONTAINMENT_SUBREAPER_UNAVAILABLE
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        prctl = libc.prctl
    except (OSError, AttributeError):
        return CONTAINMENT_SUBREAPER_UNAVAILABLE
    if prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        return CONTAINMENT_SUBREAPER_ENABLE_FAILED
    observed = ctypes.c_int(0)
    if prctl(PR_GET_CHILD_SUBREAPER, ctypes.byref(observed), 0, 0, 0) != 0:
        return CONTAINMENT_SUBREAPER_ENABLE_FAILED
    if observed.value != 1:
        return CONTAINMENT_SUBREAPER_ENABLE_FAILED
    return ""


# ══ supervisor 본체 ════════════════════════════════════════════════════
def _validate_control(message: dict) -> dict:
    argv = message["argv"]
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(item, str) and item for item in argv)
    ):
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    env = message["env"]
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    for key in ("timeout_seconds", "stdout_limit", "stderr_limit", "total_limit"):
        _require_int(message[key], minimum=1)
    for key in ("cwd", "stdout_path", "stderr_path"):
        if not isinstance(message[key], str) or not message[key]:
            raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    if message["stdin_path"] is not None and not isinstance(message["stdin_path"], str):
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)
    _require_bool(message["delete_raw"])
    return message


def _open_capture(path: str) -> int:
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)


def _file_digest(path: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
    except OSError:
        return _EMPTY_SHA256, 0
    return digest.hexdigest(), total


def _reap_nohang() -> tuple[int, dict[int, int]]:
    """수거 가능한 자식을 전부 수거한다. (개수, {pid: status})"""
    reaped: dict[int, int] = {}
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        except OSError:
            break
        if pid == 0:
            break
        reaped[pid] = status
    return len(reaped), reaped


class _Supervisor:
    """target 하나의 전 생애를 책임진다. 이 프로세스 밖 계보는 만지지 않는다."""

    def __init__(self, control: dict) -> None:
        self.control = control
        self.report: dict = {
            "returncode": -1,
            "stdout_sha256": _EMPTY_SHA256,
            "stderr_sha256": _EMPTY_SHA256,
            "stdout_bytes": 0,
            "stderr_bytes": 0,
            "timed_out": False,
            "output_limit_exceeded": False,
            "descendants_observed": 0,
            "descendants_terminated": 0,
            "descendants_reaped": 0,
            "descendant_escape_detected": False,
            "process_group_empty": False,
            "supervisor_children_empty": False,
            "raw_files_deleted": False,
            "cleanup_ok": False,
            "error_code": _NO_ERROR,
        }
        self._observed: set[int] = set()
        self._terminated: set[int] = set()
        self._reaped_pids: set[int] = set()
        self._root_killed_by_supervisor = False

    # ── 실행 ──────────────────────────────────────────────────────────
    def run(self) -> dict:
        control = self.control
        stdin_handle: int | object = subprocess.DEVNULL
        stdin_stream = None
        stdout_fd = stderr_fd = -1
        try:
            if control["stdin_path"] is not None:
                stdin_stream = open(control["stdin_path"], "rb")
                stdin_handle = stdin_stream
            stdout_fd = _open_capture(control["stdout_path"])
            stderr_fd = _open_capture(control["stderr_path"])
            try:
                process = subprocess.Popen(  # noqa: S603 - argv 배열 · shell 없음
                    control["argv"],
                    cwd=control["cwd"],
                    env=control["env"],
                    stdin=stdin_handle,
                    stdout=stdout_fd,
                    stderr=stderr_fd,
                    close_fds=True,
                    shell=False,
                    start_new_session=True,
                )
            except (OSError, ValueError):
                self.report["error_code"] = CONTAINMENT_SPAWN_FAILED
                return self._finalize()
        except OSError:
            self.report["error_code"] = CONTAINMENT_SPAWN_FAILED
            return self._finalize()
        finally:
            if stdin_stream is not None:
                stdin_stream.close()
            for fd in (stdout_fd, stderr_fd):
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

        root_pid = process.pid
        root_pgid = root_pid  # start_new_session=True → pgid == sid == pid
        root_stat = read_proc_stat(root_pid)
        root_starttime = root_stat.starttime if root_stat is not None else 0

        self._monitor_root(process, root_pid, root_pgid, root_starttime)
        self._sweep_descendants(root_pid, root_pgid)
        self._measure_output()
        return self._finalize()

    def _monitor_root(
        self, process: subprocess.Popen, root_pid: int, root_pgid: int, root_starttime: int
    ) -> None:
        control = self.control
        deadline = time.monotonic() + float(control["timeout_seconds"])
        kill_sent = False
        kill_deadline = 0.0
        while True:
            code = process.poll()
            if code is not None:
                self.report["returncode"] = code
                break
            if kill_sent and time.monotonic() > kill_deadline:
                # SIGKILL 뒤에도 수거되지 않는 root(D-state 등) — 무한 대기하지 않는다
                self.report["error_code"] = CONTAINMENT_DESCENDANT_REAP_FAILED
                break
            out_size = _safe_size(control["stdout_path"])
            err_size = _safe_size(control["stderr_path"])
            if (
                out_size > control["stdout_limit"]
                or err_size > control["stderr_limit"]
                or (out_size + err_size) > control["total_limit"]
            ):
                self.report["output_limit_exceeded"] = True
            if time.monotonic() > deadline:
                self.report["timed_out"] = True
            if (self.report["timed_out"] or self.report["output_limit_exceeded"]) and not kill_sent:
                self._root_killed_by_supervisor = True
                self._signal_group(root_pgid, signal.SIGKILL)
                kill_sent = True
                kill_deadline = time.monotonic() + 10.0
            time.sleep(_POLL_SECONDS)

    def _signal_group(self, pgid: int, signum: int) -> bool:
        try:
            os.killpg(pgid, signum)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False

    def _record_reap(self, reaped: dict[int, int]) -> None:
        self._reaped_pids.update(reaped)
        self.report["descendants_reaped"] = len(self._reaped_pids)

    def _lineage(self, root_pid: int, root_pgid: int) -> list[ProcStat]:
        me = os.getpid()
        found: dict[int, ProcStat] = {}
        for stat in living_children_of(me):
            if stat.pid != root_pid:
                found[stat.pid] = stat
        for stat in living_group_members(root_pgid, exclude=frozenset({root_pid, me})):
            found[stat.pid] = stat
        for stat in found.values():
            self._observed.add(stat.pid)
        self.report["descendants_observed"] = len(self._observed)
        return list(found.values())

    def _sweep_descendants(self, root_pid: int, root_pgid: int) -> None:
        report = self.report
        # root 는 Popen 이 reap 한다. descendants_* 는 ★후손만★ 센다.

        # ── §4-2 5항: bounded grace — 자연 종료·reap 을 기다린다 ────────
        grace_end = time.monotonic() + GRACE_SECONDS
        while time.monotonic() < grace_end:
            _count, reaped = _reap_nohang()
            self._record_reap(reaped)
            if not self._lineage(root_pid, root_pgid):
                break
            time.sleep(_POLL_SECONDS)

        survivors = self._lineage(root_pid, root_pgid)
        if survivors and not self._root_killed_by_supervisor:
            # 정상 종료한 root 가 후손을 남겼다 — 정리해도 통과로 두지 않는다(§4-3)
            report["descendant_escape_detected"] = True

        # ── §4-2 6항: 원래 PGID 에 TERM → 대기 → KILL → 대기 ───────────
        if survivors:
            self._signal_group(root_pgid, signal.SIGTERM)
            self._await_lineage_exit(root_pid, root_pgid, TERM_WAIT_SECONDS)
            if self._lineage(root_pid, root_pgid):
                self._signal_group(root_pgid, signal.SIGKILL)
                self._await_lineage_exit(root_pid, root_pgid, KILL_WAIT_SECONDS)

        # ── §4-2 7항: 재부모화된(입양된) 후손을 pidfd 로 고정해 정리 ────
        try:
            self._sweep_adopted(root_pid, root_pgid)
        except SubreaperProtocolError as exc:
            report["error_code"] = exc.code

        # ── §4-2 8항: 수거 ────────────────────────────────────────────
        _count, reaped = _reap_nohang()
        self._record_reap(reaped)

        # ── §4-2 9항: 최종 확인 ───────────────────────────────────────
        me = os.getpid()
        group_alive = living_group_members(root_pgid, exclude=frozenset({me}))
        children_alive = living_children_of(me)
        # 수거되지 않고 남은 내 zombie 자식 = reap 실패다(§4-2 8항)
        zombie_children = [
            pid for pid in _iter_proc_pids()
            if (stat := read_proc_stat(pid)) is not None
            and stat.ppid == me and stat.state == "Z"
        ]
        report["process_group_empty"] = not group_alive
        report["supervisor_children_empty"] = not children_alive and not zombie_children
        if report["error_code"] == _NO_ERROR:
            if group_alive:
                report["error_code"] = CONTAINMENT_PROCESS_GROUP_NOT_EMPTY
            elif children_alive:
                report["error_code"] = CONTAINMENT_DESCENDANT_KILL_FAILED
            elif zombie_children:
                report["error_code"] = CONTAINMENT_DESCENDANT_REAP_FAILED

    def _await_lineage_exit(self, root_pid: int, root_pgid: int, budget: float) -> None:
        end = time.monotonic() + budget
        while time.monotonic() < end:
            _count, reaped = _reap_nohang()
            self._record_reap(reaped)
            if not self._lineage(root_pid, root_pgid):
                return
            time.sleep(_POLL_SECONDS)

    def _sweep_adopted(self, root_pid: int, root_pgid: int) -> None:
        for _round in range(10):
            survivors = self._lineage(root_pid, root_pgid)
            if not survivors:
                return
            pinned: list[_PinnedProcess] = []
            try:
                for stat in survivors:
                    pinned.append(pin_process(stat.pid, stat.starttime))
                for handle in pinned:
                    if handle.signal(signal.SIGTERM):
                        self._terminated.add(handle.pid)
                self._await_lineage_exit(root_pid, root_pgid, TERM_WAIT_SECONDS)
                for handle in pinned:
                    if handle.signal(signal.SIGKILL):
                        self._terminated.add(handle.pid)
                self._await_lineage_exit(root_pid, root_pgid, KILL_WAIT_SECONDS)
            finally:
                for handle in pinned:
                    handle.close()
                self.report["descendants_terminated"] = len(self._terminated)

    def _measure_output(self) -> None:
        control = self.control
        out_digest, out_bytes = _file_digest(control["stdout_path"])
        err_digest, err_bytes = _file_digest(control["stderr_path"])
        self.report.update(
            stdout_sha256=out_digest, stdout_bytes=out_bytes,
            stderr_sha256=err_digest, stderr_bytes=err_bytes,
        )

    def _finalize(self) -> dict:
        report = self.report
        deleted = True
        if self.control["delete_raw"]:
            deleted = _delete_files(
                (self.control["stdout_path"], self.control["stderr_path"])
            )
            report["raw_files_deleted"] = deleted
            if not deleted and report["error_code"] == _NO_ERROR:
                report["error_code"] = CONTAINMENT_RAW_DELETE_FAILED
        report["cleanup_ok"] = (
            report["process_group_empty"]
            and report["supervisor_children_empty"]
            and (deleted if self.control["delete_raw"] else True)
        )
        # 우선순위: 상한 초과 > 시간 초과 > 이탈 후손 (기존 계약과 같은 순서)
        if report["error_code"] == _NO_ERROR:
            if report["output_limit_exceeded"]:
                report["error_code"] = CONTAINMENT_OUTPUT_TOO_LARGE
            elif report["timed_out"]:
                report["error_code"] = CONTAINMENT_TIMEOUT
            elif report["descendant_escape_detected"]:
                report["error_code"] = CONTAINMENT_DESCENDANT_SURVIVED_ROOT
        return report


def _safe_size(path: str) -> int:
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def _delete_files(paths: Sequence[str]) -> bool:
    ok = True
    for path in paths:
        try:
            os.unlink(path)
        except FileNotFoundError:
            continue
        except OSError:
            ok = False
    return ok


def _supervisor_main() -> int:
    """supervisor 프로세스 진입점. 보고는 stdout 의 JSON 한 건뿐이다."""
    def emit(report: dict) -> int:
        payload = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        if len(payload.encode("utf-8")) > MAX_MESSAGE_BYTES:
            payload = json.dumps(
                {**_error_report(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)},
                ensure_ascii=False, separators=(",", ":"),
            )
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()
        return 0

    failure = enable_child_subreaper()
    if failure:
        return emit(_error_report(failure))

    raw = sys.stdin.buffer.read(MAX_MESSAGE_BYTES + 1)
    try:
        control = _validate_control(_parse_message(raw, required_keys=_CONTROL_KEYS))
    except SubreaperProtocolError as exc:
        return emit(_error_report(exc.code))

    try:
        report = _Supervisor(control).run()
    except SubreaperProtocolError as exc:
        return emit(_error_report(exc.code))
    except Exception:  # noqa: BLE001 - traceback 을 부모·로그로 흘리지 않는다(§4-4)
        return emit(_error_report(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR))
    return emit(report)


def _error_report(code: str) -> dict:
    return {
        "returncode": -1,
        "stdout_sha256": _EMPTY_SHA256,
        "stderr_sha256": _EMPTY_SHA256,
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "timed_out": False,
        "output_limit_exceeded": False,
        "descendants_observed": 0,
        "descendants_terminated": 0,
        "descendants_reaped": 0,
        "descendant_escape_detected": False,
        "process_group_empty": False,
        "supervisor_children_empty": False,
        "raw_files_deleted": False,
        "cleanup_ok": False,
        "error_code": code if code in _ERROR_CODE_ALLOWLIST else CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR,
    }


# ══ 부모 쪽: supervisor 를 만들어 한 명령을 감독시킨다 ══════════════════
def _supervisor_argv() -> list[str]:
    return [sys.executable, "-m", "ac25.linux_subreaper"]


def _supervisor_env() -> dict[str, str]:
    """supervisor 에 주는 env 는 allowlist 다. os.environ 전체를 넘기지 않는다."""
    allowed: dict[str, str] = {
        # ac25 패키지를 찾을 경로는 이 파일 위치에서 유도한다 — 입력이 아니다.
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONNOUSERSITE": "1",
    }
    for key in ("PATH", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value is not None:
            allowed[key] = value
    return allowed


def supervise(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    stdout_path: Path,
    stderr_path: Path,
    stdout_limit: int,
    stderr_limit: int,
    total_limit: int,
    stdin_path: Path | None = None,
    delete_raw: bool = True,
    spawn: Callable[..., subprocess.Popen] | None = None,
) -> SupervisorReport:
    """별도 supervisor 프로세스로 argv 를 실행하고 보고 한 건을 받는다.

    ★토큰이 든 env 는 argv 가 아니라 stdin 의 제어 메시지로만 넘어간다.
    ★spawn 은 시험 주입점이다. production 은 기본값으로만 부른다.
    """
    control = {
        "argv": list(argv),
        "cwd": str(cwd),
        "env": dict(env),
        "timeout_seconds": int(timeout_seconds),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_limit": int(stdout_limit),
        "stderr_limit": int(stderr_limit),
        "total_limit": int(total_limit),
        "stdin_path": str(stdin_path) if stdin_path is not None else None,
        "delete_raw": bool(delete_raw),
    }
    payload = json.dumps(control, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR)

    launcher = spawn if spawn is not None else subprocess.Popen
    try:
        supervisor = launcher(  # noqa: S603 - argv 배열 · shell 없음
            _supervisor_argv(),
            cwd=str(cwd),
            env=_supervisor_env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            close_fds=True,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_DIED) from exc

    budget = float(timeout_seconds) + _SUPERVISOR_EXTRA_BUDGET_SECONDS
    try:
        out, _err = supervisor.communicate(input=payload, timeout=budget)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(supervisor.pid, signal.SIGKILL)
        except OSError:
            pass
        supervisor.wait(timeout=5)
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_DIED) from None

    if supervisor.returncode != 0 or not out:
        raise SubreaperProtocolError(CONTAINMENT_SUPERVISOR_DIED)
    return parse_report(out.strip())


if __name__ == "__main__":
    raise SystemExit(_supervisor_main())


__all__ = [
    "CONTAINMENT_DESCENDANT_KILL_FAILED",
    "CONTAINMENT_DESCENDANT_REAP_FAILED",
    "CONTAINMENT_DESCENDANT_SURVIVED_ROOT",
    "CONTAINMENT_DESCENDANT_TERM_FAILED",
    "CONTAINMENT_PROCESS_GROUP_NOT_EMPTY",
    "CONTAINMENT_PROCESS_IDENTITY_UNPROVEN",
    "CONTAINMENT_RAW_DELETE_FAILED",
    "CONTAINMENT_SUBREAPER_ENABLE_FAILED",
    "CONTAINMENT_SUBREAPER_UNAVAILABLE",
    "CONTAINMENT_SUPERVISOR_DIED",
    "CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR",
    "GRACE_SECONDS",
    "KILL_WAIT_SECONDS",
    "MAX_MESSAGE_BYTES",
    "ProcStat",
    "SubreaperProtocolError",
    "SupervisorReport",
    "TERM_WAIT_SECONDS",
    "enable_child_subreaper",
    "living_children_of",
    "living_group_members",
    "parse_report",
    "pin_process",
    "read_proc_stat",
    "supervise",
]
