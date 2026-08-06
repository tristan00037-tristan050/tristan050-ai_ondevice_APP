"""F-02 — procfs 관측 불능은 ★fail-open 이 아니라 fail-closed★ 인가.

감사 F-02 판정
    A안은 `/proc/<pid>/stat` 읽기 실패를 "이미 종료됨" 과 같은 `None` 으로
    합친다. 그러면 ★관측 수단이 사라졌을 때 "후손이 없다" 로 판정★ 한다.

관측할 수 없는 것과 없는 것은 다르다. 후자는 사실이고 전자는 무지다.
무지를 사실로 적으면, 격리가 뚫린 그 순간에 초록불이 켜진다.

    없음(ENOENT·ESRCH)  → None      이미 종료했다. 사실이다.
    그 밖의 OSError     → 닫는다    읽을 수 없다. 사실을 모른다.
    파싱 실패           → 닫는다    형식이 예상과 다르다. 사실을 모른다.
    /proc 열거 실패     → 닫는다    계보를 셀 수 없다.
"""
from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest
from ac25 import linux_subreaper as ls

pytestmark = pytest.mark.no_sidecar_token

requires_linux = pytest.mark.skipif(sys.platform != "linux", reason="R6-1 은 Linux 전용")


# ══ 종료한 프로세스는 사실이다 — None ══════════════════════════════════
@requires_linux
def test_exited_process_reads_as_none_not_an_error():
    """이미 종료한 PID 는 관측 실패가 아니라 ★없다는 사실★ 이다."""
    absent = 4_194_303  # PID_MAX 부근 — 존재할 가능성이 사실상 없다
    while Path(f"/proc/{absent}").exists():
        absent -= 1
    assert ls.read_proc_stat(absent) is None


@requires_linux
def test_self_is_readable():
    stat = ls.read_proc_stat(os.getpid())
    assert stat is not None
    assert stat.pid == os.getpid()
    assert stat.state not in ("Z", "X")


# ══ 관측 불능은 닫는다 ═════════════════════════════════════════════════
@pytest.mark.parametrize(
    "error",
    [
        PermissionError(errno.EACCES, "Permission denied"),
        OSError(errno.EIO, "I/O error"),
        OSError(errno.ENOTDIR, "Not a directory"),
    ],
)
def test_unreadable_stat_is_fail_closed(monkeypatch, error):
    """권한 부족·hidepid·I/O 오류를 '종료함' 으로 바꾸지 않는다."""
    def explode(self, *args, **kwargs):
        raise error

    monkeypatch.setattr(Path, "read_bytes", explode)
    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls.read_proc_stat(1)
    assert caught.value.code == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN


@pytest.mark.parametrize(
    "body",
    [
        b"",                                  # 빈 내용
        b"1 (init) S",                        # 필드 부족
        b"garbage without the marker",        # ') ' 없음
        b"1 (init) S notanumber 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20",
    ],
)
def test_malformed_stat_is_fail_closed(monkeypatch, body):
    """형식이 예상과 다르면 파싱을 포기하고 닫는다. 추측하지 않는다."""
    monkeypatch.setattr(Path, "read_bytes", lambda self, *a, **k: body)
    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls.read_proc_stat(1)
    assert caught.value.code == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN


def test_proc_enumeration_failure_is_fail_closed(monkeypatch):
    """/proc 를 열거하지 못하면 '후손 0' 이 아니라 ★모른다★ 이다."""
    def explode(path):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(os, "listdir", explode)
    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls._iter_proc_pids()
    assert caught.value.code == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN


def test_lineage_enumeration_propagates_the_failure(monkeypatch):
    """계보 열거도 같은 규칙이다 — 빈 목록으로 바꾸지 않는다."""
    monkeypatch.setattr(
        os, "listdir",
        lambda path: (_ for _ in ()).throw(PermissionError(errno.EACCES, "denied")),
    )
    for enumerate_lineage in (
        lambda: ls.living_children_of(os.getpid()),
        lambda: ls.living_group_members(os.getpgrp()),
    ):
        with pytest.raises(ls.SubreaperProtocolError) as caught:
            enumerate_lineage()
        assert caught.value.code == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN


# ══ supervisor 는 시작 전에 관측 가능성을 확인한다 ═════════════════════
@requires_linux
def test_require_procfs_passes_when_proc_is_usable():
    ls.require_procfs()  # 예외가 없으면 통과


def test_require_procfs_closes_when_self_stat_is_unreadable(monkeypatch):
    monkeypatch.setattr(
        Path, "read_bytes",
        lambda self, *a, **k: (_ for _ in ()).throw(FileNotFoundError("no /proc")),
    )
    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls.require_procfs()
    assert caught.value.code == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN


def test_require_procfs_closes_when_self_stat_is_malformed(monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda self, *a, **k: b"no marker here")
    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls.require_procfs()
    assert caught.value.code == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN


def test_require_procfs_closes_when_enumeration_is_blocked(monkeypatch):
    """읽기는 되는데 열거가 막힌 경우도 잡는다."""
    monkeypatch.setattr(Path, "read_bytes", lambda self, *a, **k: b"1 (init) S 0 1 " + b"0 " * 20)
    monkeypatch.setattr(
        os, "listdir",
        lambda path: (_ for _ in ()).throw(PermissionError(errno.EACCES, "denied")),
    )
    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls.require_procfs()
    assert caught.value.code == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN


def test_supervisor_checks_procfs_before_reading_control(monkeypatch):
    """★제어 메시지를 읽기 전에 관측 가능성을 본다.

    순서가 반대면, 관측할 수 없는 환경에서 명령을 먼저 실행한 뒤에야 닫는다.
    """
    source = (
        Path(__file__).resolve().parents[2]
        / "scripts" / "ci" / "ac25" / "linux_subreaper.py"
    ).read_text(encoding="utf-8")
    body = source.partition("def _supervisor_main(")[2]
    require_index = body.index("require_procfs()")
    stdin_index = body.index("sys.stdin.buffer.read")
    assert require_index < stdin_index, "제어 메시지를 먼저 읽는다"


# ══ 오류 코드가 계약에 있다 ════════════════════════════════════════════
def test_identity_unproven_is_a_reportable_code():
    from ac25 import output_containment as oc

    assert ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN in ls._ERROR_CODE_ALLOWLIST
    assert oc.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN
    report = ls._error_report(ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN)
    assert report["error_code"] == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN
    assert report["cleanup_ok"] is False
    assert report["process_group_empty"] is False
    assert report["supervisor_children_empty"] is False


def test_unproven_identity_never_reports_an_empty_group():
    """★관측 불능일 때 '그룹이 비었다' 로 적지 않는다 — 그것이 fail-open 이다."""
    report = ls._error_report(ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN)
    parsed = ls.parse_report(
        __import__("json").dumps(report, separators=(",", ":")).encode("utf-8")
    )
    assert parsed.process_group_empty is False
    assert parsed.supervisor_children_empty is False
    assert parsed.descendants_observed == 0
    assert parsed.cleanup_ok is False
