"""§4-2 · §4-4 R6-1 — 전용 subreaper supervisor 단위 시험.

공격 시험(정상 종료·stdio 분리·setsid 이탈 등)은 test_output_containment.py 가
격리기 전체 경로로 돌린다. 이 파일은 그 아래 계층을 직접 본다.

    subreaper 설정과 재확인
    supervisor 통신 계약(잘림·초과·알 수 없는 키·중복 키·음수·잘못된 digest)
    PID 재사용 방어(pidfd 우선 · starttime 대안 · 둘 다 불가면 fail-closed)
    supervisor 강제 종료
    raw 임시파일 삭제 실패
    /proc 열거가 ★계보 기준★ 이지 이름 기준이 아님
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from ac25 import linux_subreaper as ls

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
# ★v2.0 §4-2 — 양성 시험은 ★실제 /proc 계보 관측★ 이 되는 환경에서만 뜻이 있다.
#   Linux 라고 /proc 이 있는 것은 아니다(컨테이너·hidepid·chroot).
#   관측 불가 환경에서는 conftest 가 ★수집에서 제외★ 한다(skip 이 아니다).
#   ★부정 시험에는 붙이지 않는다 — 그 환경이야말로 부정 시험이 필요한 곳이다.
requires_procfs = pytest.mark.requires_procfs


def _report_payload(**overrides) -> bytes:
    base = {
        "returncode": 0,
        "stdout_sha256": "0" * 64,
        "stderr_sha256": "0" * 64,
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "timed_out": False,
        "output_limit_exceeded": False,
        "descendants_observed": 0,
        "descendants_terminated": 0,
        "descendants_reaped": 0,
        "descendant_escape_detected": False,
        "process_group_empty": True,
        "supervisor_children_empty": True,
        "raw_files_deleted": True,
        "cleanup_ok": True,
        "error_code": "NONE",
    }
    base.update(overrides)
    return json.dumps(base).encode("utf-8")


# ══ subreaper 설정 ═════════════════════════════════════════════════════
@requires_procfs
def test_child_subreaper_can_be_enabled_and_verified():
    """자식 프로세스에서 걸어 본다 — 시험 프로세스 자신을 subreaper 로 만들지 않는다."""
    code = (
        "import sys; sys.path.insert(0, %r);"
        "from ac25.linux_subreaper import enable_child_subreaper;"
        "print(enable_child_subreaper() or 'OK')"
        % str(REPO_ROOT / "scripts" / "ci")
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert done.stdout.strip() == "OK", done.stdout + done.stderr


def test_subreaper_is_not_enabled_on_the_verifier_process():
    """§4-2 — 메인 검증 프로세스를 subreaper 로 만들지 않는다."""
    source = (REPO_ROOT / "scripts/ci/ac25/output_containment.py").read_text(encoding="utf-8")
    assert "enable_child_subreaper" not in source


# ══ §4-4 통신 계약 ═════════════════════════════════════════════════════
def test_valid_report_parses():
    report = ls.parse_report(_report_payload())
    assert report.error_code == "NONE"
    assert report.cleanup_ok is True


@pytest.mark.parametrize(
    "raw",
    [
        b"",                                   # 빈 메시지
        b"{",                                  # 잘린 JSON
        b"[]",                                 # 객체가 아님
        b'{"returncode": 0}',                  # 키 누락
    ],
)
def test_malformed_report_is_a_protocol_error(raw):
    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls.parse_report(raw)
    assert caught.value.code == ls.CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR


def test_unknown_key_is_rejected():
    payload = json.loads(_report_payload())
    payload["surprise"] = 1
    with pytest.raises(ls.SubreaperProtocolError):
        ls.parse_report(json.dumps(payload).encode("utf-8"))


def test_duplicate_key_is_rejected():
    raw = b'{"error_code":"NONE","error_code":"NONE"}'
    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls.parse_report(raw)
    assert caught.value.code == ls.CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR


def test_oversized_message_is_rejected():
    filler = "x" * (ls.MAX_MESSAGE_BYTES + 16)
    with pytest.raises(ls.SubreaperProtocolError):
        ls.parse_report(json.dumps({"error_code": filler}).encode("utf-8"))


@pytest.mark.parametrize("field", ["descendants_observed", "descendants_terminated", "stdout_bytes"])
def test_negative_counts_are_rejected(field):
    with pytest.raises(ls.SubreaperProtocolError):
        ls.parse_report(_report_payload(**{field: -1}))


@pytest.mark.parametrize("digest", ["", "0" * 63, "0" * 65, "Z" * 64, 12345])
def test_bad_digest_is_rejected(digest):
    with pytest.raises(ls.SubreaperProtocolError):
        ls.parse_report(_report_payload(stdout_sha256=digest))


def test_unknown_error_code_is_rejected():
    with pytest.raises(ls.SubreaperProtocolError):
        ls.parse_report(_report_payload(error_code="MADE_UP_CODE"))


def test_report_carries_no_raw_output_fields():
    fields = set(ls.SupervisorReport.__dataclass_fields__)
    for forbidden in ("stdout", "stderr", "traceback", "argv", "env"):
        assert forbidden not in fields


def test_supervisor_never_sends_a_traceback():
    """§4-4 — 예외 유형은 허용 목록 코드로만 나간다."""
    source = (REPO_ROOT / "scripts/ci/ac25/linux_subreaper.py").read_text(encoding="utf-8")
    assert "traceback" not in source.replace("traceback 을", "").replace("traceback·", "")
    assert "_ERROR_CODE_ALLOWLIST" in source


# ══ supervisor 강제 종료 ═══════════════════════════════════════════════
@requires_procfs
def test_supervisor_death_is_fail_closed(tmp_path):
    """supervisor 가 보고 없이 죽으면 성공으로 세지 않는다."""

    def dying_spawn(*_args, **kwargs):
        return subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", "import os; os._exit(9)"],
            stdin=kwargs.get("stdin"), stdout=kwargs.get("stdout"),
            stderr=kwargs.get("stderr"), close_fds=True, start_new_session=True,
        )

    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls.supervise(
            [sys.executable, "-c", "pass"],
            cwd=REPO_ROOT, env={}, timeout_seconds=5,
            stdout_path=tmp_path / "o.bin", stderr_path=tmp_path / "e.bin",
            stdout_limit=1024, stderr_limit=1024, total_limit=2048,
            spawn=dying_spawn,
        )
    assert caught.value.code == ls.CONTAINMENT_SUPERVISOR_DIED


@requires_procfs
def test_supervisor_emitting_garbage_is_a_protocol_error(tmp_path):
    def noisy_spawn(*_args, **kwargs):
        return subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", "import sys; sys.stdin.read(); print('not json')"],
            stdin=kwargs.get("stdin"), stdout=kwargs.get("stdout"),
            stderr=kwargs.get("stderr"), close_fds=True, start_new_session=True,
        )

    with pytest.raises(ls.SubreaperProtocolError) as caught:
        ls.supervise(
            [sys.executable, "-c", "pass"],
            cwd=REPO_ROOT, env={}, timeout_seconds=5,
            stdout_path=tmp_path / "o.bin", stderr_path=tmp_path / "e.bin",
            stdout_limit=1024, stderr_limit=1024, total_limit=2048,
            spawn=noisy_spawn,
        )
    assert caught.value.code == ls.CONTAINMENT_SUPERVISOR_PROTOCOL_ERROR


# ══ PID 재사용 방어 ════════════════════════════════════════════════════
@requires_procfs
def test_pin_process_refuses_a_recycled_pid():
    """같은 PID 인데 starttime 이 다르면 신호를 보내지 않고 닫는다."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        stat = ls.read_proc_stat(child.pid)
        assert stat is not None
        # pidfd 를 쓰지 못하는 환경을 가정해 starttime 경로를 직접 검증한다
        handle = ls._PinnedProcess(child.pid, stat.starttime + 1, None)
        with pytest.raises(ls.SubreaperProtocolError) as caught:
            handle.signal(0)
        assert caught.value.code == ls.CONTAINMENT_PROCESS_IDENTITY_UNPROVEN
    finally:
        child.kill()
        child.wait(timeout=5)


@requires_procfs
def test_pin_process_uses_pidfd_when_available():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        stat = ls.read_proc_stat(child.pid)
        handle = ls.pin_process(child.pid, stat.starttime)
        try:
            if hasattr(os, "pidfd_open"):
                assert handle.pidfd is not None
            assert handle.signal(0) is True
        finally:
            handle.close()
    finally:
        child.kill()
        child.wait(timeout=5)


@requires_procfs
def test_pin_process_on_exited_pid_reports_not_signalled():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=5)
    handle = ls.pin_process(child.pid, 0)
    try:
        assert handle.signal(0) is False
    finally:
        handle.close()


def test_identity_unproven_code_exists_for_fail_closed_path():
    source = (REPO_ROOT / "scripts/ci/ac25/linux_subreaper.py").read_text(encoding="utf-8")
    assert "CONTAINMENT_PROCESS_IDENTITY_UNPROVEN" in source
    assert "pidfd_open" in source and "pidfd_send_signal" in source


# ══ raw 임시파일 삭제 ══════════════════════════════════════════════════
def test_delete_files_reports_failure_for_an_undeletable_path(tmp_path):
    """unlink 할 수 없는 대상은 삭제 성공으로 세지 않는다."""
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    assert ls._delete_files([str(directory)]) is False
    # 이미 없는 파일은 실패가 아니다 — 지울 것이 없는 상태가 목표이기 때문이다
    assert ls._delete_files([str(tmp_path / "absent.bin")]) is True


def test_raw_delete_failure_closes_the_run(tmp_path):
    """§4-3 — raw 를 지우지 못하면 정리 성공으로 반환하지 않는다."""
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    supervisor = ls._Supervisor({
        "argv": [sys.executable, "-c", "pass"],
        "cwd": str(tmp_path),
        "env": {},
        "timeout_seconds": 10,
        "stdout_path": str(blocked),           # 디렉터리라 unlink 가 실패한다
        "stderr_path": str(tmp_path / "e.bin"),
        "stdout_limit": 1024,
        "stderr_limit": 1024,
        "total_limit": 2048,
        "stdin_path": None,
        "delete_raw": True,
    })
    supervisor.report["process_group_empty"] = True
    supervisor.report["supervisor_children_empty"] = True
    report = supervisor._finalize()
    assert report["raw_files_deleted"] is False
    assert report["error_code"] == ls.CONTAINMENT_RAW_DELETE_FAILED
    assert report["cleanup_ok"] is False


@requires_procfs
def test_raw_files_are_deleted_on_success(tmp_path):
    out = tmp_path / "stdout.bin"
    err = tmp_path / "stderr.bin"
    report = ls.supervise(
        [sys.executable, "-c", "print('x')"],
        cwd=REPO_ROOT, env={}, timeout_seconds=10,
        stdout_path=out, stderr_path=err,
        stdout_limit=1 << 20, stderr_limit=1 << 20, total_limit=1 << 21,
        delete_raw=True,
    )
    assert report.raw_files_deleted is True
    assert not out.exists() and not err.exists()
    assert report.stdout_bytes == 2  # "x\n" — 삭제 전에 실측했다


# ══ /proc 열거는 계보 기준이다 ═════════════════════════════════════════
def test_enumeration_is_by_lineage_not_by_name():
    """★코드★ 안에 이름 기반 종료 수단이 없어야 한다(주석 문장이 아니라 실행 코드).

    /proc 를 읽는 경로는 stat 하나뿐이며, cmdline·comm 으로 프로세스를 고르지
    않는다. 이름으로 고르면 무관한 프로세스를 죽일 수 있다.
    """
    import ast as _ast

    source = (REPO_ROOT / "scripts/ci/ac25/linux_subreaper.py").read_text(encoding="utf-8")
    tree = _ast.parse(source, filename="linux_subreaper.py")
    literals: list[str] = []
    identifiers: list[str] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Constant) and isinstance(node.value, str):
            # 모듈·함수 docstring 은 설명문이므로 제외한다
            literals.append(node.value)
        elif isinstance(node, _ast.Attribute):
            identifiers.append(node.attr)
        elif isinstance(node, _ast.Name):
            identifiers.append(node.id)
    docstrings = {
        _ast.get_docstring(node, clean=False) or ""
        for node in _ast.walk(tree)
        if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.ClassDef))
    }
    code_literals = [text for text in literals if text not in docstrings]
    for forbidden in ("pkill", "killall", "cmdline", "/proc/self/task"):
        assert not any(forbidden in text for text in code_literals), forbidden
        assert forbidden not in identifiers, forbidden
    # /proc 접근은 stat 과 디렉터리 열거뿐이다
    # f-string 조각까지 포함해 /proc 경로 문자열은 이 둘뿐이다(디렉터리 열거와 stat)
    proc_literals = sorted({text for text in code_literals if text.startswith("/proc")})
    # /proc/self/stat 은 F-02 가 요구한 ★관측 가능성 확인★ 이다. 자기 자신을 stat
    # 하는 것이므로 이름 기반 탐색이 아니고 다른 계보를 보지도 않는다.
    assert proc_literals == ["/proc", "/proc/", "/proc/self/stat"], proc_literals
    assert 'Path(f"/proc/{pid}/stat")' in source
    assert 'os.listdir("/proc")' in source
    assert source.count('"/proc/self/stat"') == 1, "관측 확인은 한 자리에서만 한다"
    assert "stat.ppid == parent_pid" in source
    assert "stat.pgrp == pgid" in source


@requires_procfs
def test_living_children_sees_only_my_children():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        time.sleep(0.2)
        mine = {stat.pid for stat in ls.living_children_of(os.getpid())}
        assert child.pid in mine and other.pid in mine
        # 내 부모의 자식을 내 자식으로 세지 않는다
        assert os.getpid() not in mine
    finally:
        for process in (child, other):
            process.kill()
            process.wait(timeout=5)


@requires_procfs
def test_zombie_is_not_counted_as_living():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.poll()
    time.sleep(0.2)
    stat = ls.read_proc_stat(child.pid)
    if stat is not None and stat.state == "Z":
        assert child.pid not in {item.pid for item in ls.living_children_of(os.getpid())}
    child.wait(timeout=5)


def test_read_proc_stat_handles_comm_with_spaces_and_parens(tmp_path, monkeypatch):
    """comm 에 공백·괄호가 있어도 필드 위치를 잃지 않는다."""
    fake = tmp_path / "stat"
    fields = " ".join(str(index) for index in range(3, 24))
    fake.write_text(f"4242 (weird )name) S {fields}\n")

    original = Path.read_bytes

    def patched(self):
        if str(self) == "/proc/4242/stat":
            return fake.read_bytes()
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", patched)
    stat = ls.read_proc_stat(4242)
    assert stat is not None
    assert stat.state == "S"
    assert stat.ppid == 3
