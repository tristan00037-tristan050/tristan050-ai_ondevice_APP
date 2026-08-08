"""§4-5 · §5-7 — 출력 격리 + 후손 완전 정리 시험.

감사 C1: CLI 가 두 줄만 내도 자식이 부모 stream 을 상속하면 traceback·절대경로가
Actions log 로 직행한다. 그리고 R6-1: 부모가 정상 종료해도 setsid 로 이탈한
후손이 남으면 격리는 뚫린 것이다.

★가짜 실패·이탈 subprocess 를 실제로 돌려 부모 stdout·stderr 가 비어 있는지 본다.
★정상 종료·stdio 분리·setsid 이탈·timeout·출력 초과 후손을 모두 발동시킨다.
★production tree 를 AST 로 전수 조사해 격리기 밖 process 호출이 0 인지 본다.
"""
from __future__ import annotations

import ast
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from ac25 import linux_subreaper as ls
from ac25 import output_containment as oc

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DIR = REPO_ROOT / "scripts" / "ci" / "ac25"
# ★process 를 실제로 실행하는 모듈은 정확히 이 둘뿐이다.
PROCESS_MODULES = ("output_containment.py", "linux_subreaper.py")
WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("box5-ac25-*.yml"))

FORBIDDEN_MODULES = ("subprocess", "asyncio.subprocess")
FORBIDDEN_ATTRS = (
    "system", "popen", "execv", "execve", "execl", "execlp", "execvp",
    "posix_spawn", "posix_spawnp", "create_subprocess_exec", "create_subprocess_shell",
)

MARKER = "AC25_SECRET_MARKER_DO_NOT_LEAK"


def _other_modules() -> list[Path]:
    return [p for p in sorted(PRODUCTION_DIR.glob("*.py")) if p.name not in PROCESS_MODULES]


# ══ AST 전수 조사 — 격리기 밖 process API 0건 ═════════════════════════
def test_no_production_module_imports_process_apis():
    for path in _other_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in FORBIDDEN_MODULES, f"{path.name}: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "") not in FORBIDDEN_MODULES, path.name


def test_no_production_module_calls_process_apis():
    for path in _other_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            attr = getattr(node.func, "attr", None)
            assert attr not in FORBIDDEN_ATTRS, f"{path.name} 이 {attr}() 를 부른다"


def test_only_the_two_process_modules_name_subprocess():
    """subprocess 는 output_containment 와 linux_subreaper 만 안다."""
    offenders = [
        path.name for path in _other_modules()
        if "subprocess" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], offenders


def test_no_shell_true_anywhere():
    for path in sorted(PRODUCTION_DIR.glob("*.py")):
        assert "shell=True" not in path.read_text(encoding="utf-8"), path.name
    for path in WORKFLOWS:
        assert "shell=True" not in path.read_text(encoding="utf-8"), path.name


def test_only_the_subreaper_spawns_and_it_isolates_the_session():
    """★실제로 process 를 만드는 자리는 linux_subreaper 하나다(R6-1).

    output_containment 는 그 supervisor 를 통해서만 실행하므로 Popen 을 부르지
    않는다. supervisor 가 target 과 자신을 모두 새 session 으로 연다.
    """
    subreaper = (PRODUCTION_DIR / "linux_subreaper.py").read_text(encoding="utf-8")
    assert subreaper.count("shell=False") >= 2
    assert subreaper.count("start_new_session=True") >= 2

    containment = (PRODUCTION_DIR / "output_containment.py").read_text(encoding="utf-8")
    tree = ast.parse(containment, filename="output_containment.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            attr = getattr(node.func, "attr", None)
            assert attr != "Popen", "격리기가 supervisor 를 우회해 직접 실행한다"
    assert "linux_subreaper.supervise" in containment


def test_seven_modules_were_migrated():
    """§3 실측이 지목한 일곱이 전부 격리기를 쓴다."""
    expected = {
        "approval_signature.py", "git_paths.py", "integration_merge.py",
        "lock_verifier.py", "orchestrator.py", "remote_facts.py", "stage_b_runner.py",
    }
    users = {
        path.name for path in _other_modules()
        if "output_containment" in path.read_text(encoding="utf-8")
    }
    assert expected <= users, expected - users


# ══ 시험 도구 ══════════════════════════════════════════════════════════
@pytest.fixture
def runner_temp(tmp_path) -> Path:
    root = tmp_path / "runner"
    root.mkdir()
    return root


def _script(body: str) -> list[str]:
    return [sys.executable, "-c", body]


def _script_file(tmp_path: Path, name: str, body: str) -> list[str]:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return [sys.executable, str(path)]


def _pid_alive(pid: int) -> bool:
    stat = ls.read_proc_stat(pid)
    return stat is not None and stat.state not in ("Z", "X")


def _read_pids(control: Path, expected: int, *, deadline: float = 5.0) -> list[int]:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if control.exists():
            lines = [line for line in control.read_text().splitlines() if line.strip()]
            if len(lines) >= expected:
                return [int(line) for line in lines[:expected]]
        time.sleep(0.02)
    return [int(line) for line in control.read_text().splitlines() if line.strip()] if control.exists() else []


# ★v2.0 §4-2 — 양성 시험은 ★실제 /proc 계보 관측★ 이 되는 환경에서만 뜻이 있다.
#   Linux 라고 /proc 이 있는 것은 아니다(컨테이너·hidepid·chroot).
#   관측 불가 환경에서는 conftest 가 ★수집에서 제외★ 한다(skip 이 아니다).
#   ★부정 시험에는 붙이지 않는다 — 그 환경이야말로 부정 시험이 필요한 곳이다.
requires_procfs = pytest.mark.requires_procfs


# ══ 부모 stream 에 아무것도 안 남는다 (RAW_OUTPUT_EMITTED=0) ════════════
def test_child_traceback_never_reaches_the_parent(capfd, runner_temp):
    result = oc.run_contained(
        _script(f"raise RuntimeError('{MARKER}')"),
        cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=60, runner_temp=runner_temp,
    )
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert MARKER not in captured.out and MARKER not in captured.err
    # 자식은 실제로 실패했고 그 사실은 digest·bytes 로 남는다(원문은 아니다)
    assert result.returncode != 0
    assert result.stderr_bytes > 0
    assert result.stderr_sha256 != ls._EMPTY_SHA256


def test_run_and_read_returns_bytes_for_parsing_but_parent_stays_clean(capfd, runner_temp):
    code, out, err = oc.run_and_read(
        _script(f"import sys; sys.stderr.write('{MARKER}')"),
        cwd=REPO_ROOT, runner_temp=runner_temp,
    )
    captured = capfd.readouterr()
    assert captured.out == "" and captured.err == ""
    assert MARKER.encode() in err  # 분류용 bytes 로만 돌아온다
    assert code == 0


def test_error_message_carries_only_a_code(runner_temp):
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script("import time; time.sleep(60)"),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=1, runner_temp=runner_temp,
        )
    message = str(caught.value)
    assert message == oc.CONTAINMENT_TIMEOUT
    assert "/" not in message and MARKER not in message


# ══ §4-5 공격 — 정상 종료 + 지속 손자 ═════════════════════════════════
@requires_procfs
def test_normal_exit_with_persistent_grandchild_is_detected(runner_temp, tmp_path):
    control = tmp_path / "pids.txt"
    body = f"""
import os, sys, time
pid = os.fork()
if pid == 0:
    child = os.fork()
    if child == 0:
        open({str(control)!r}, "a").write(str(os.getpid()) + "\\n")
        time.sleep(120)
        os._exit(0)
    os._exit(0)
os.waitpid(pid, 0)
time.sleep(0.4)
sys.exit(0)
"""
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script_file(tmp_path, "attack1.py", body),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=30, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_DESCENDANT_SURVIVED_ROOT
    for pid in _read_pids(control, 1):
        assert not _pid_alive(pid), f"grandchild {pid} 이 살아남았다"


@requires_procfs
def test_grandchild_with_detached_stdio_is_still_detected(runner_temp, tmp_path):
    control = tmp_path / "pids.txt"
    body = f"""
import os, sys, time
pid = os.fork()
if pid == 0:
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1); os.dup2(devnull, 2)
    open({str(control)!r}, "a").write(str(os.getpid()) + "\\n")
    time.sleep(120)
    os._exit(0)
os.waitpid(pid, 0) if False else None
time.sleep(0.4)
sys.exit(0)
"""
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script_file(tmp_path, "attack2.py", body),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=30, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_DESCENDANT_SURVIVED_ROOT
    for pid in _read_pids(control, 1):
        assert not _pid_alive(pid)


@requires_procfs
def test_double_fork_setsid_escape_is_detected(runner_temp, tmp_path):
    control = tmp_path / "pids.txt"
    body = f"""
import os, sys, time
pid = os.fork()
if pid == 0:
    os.setsid()
    grandchild = os.fork()
    if grandchild == 0:
        open({str(control)!r}, "a").write(str(os.getpid()) + "\\n")
        time.sleep(120)
        os._exit(0)
    os._exit(0)
os.waitpid(pid, 0)
time.sleep(0.4)
sys.exit(0)
"""
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script_file(tmp_path, "attack3.py", body),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=30, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_DESCENDANT_SURVIVED_ROOT
    pids = _read_pids(control, 1)
    assert pids, "setsid 손자 PID 를 얻지 못했다"
    for pid in pids:
        assert not _pid_alive(pid), f"setsid 이탈 손자 {pid} 가 살아남았다"


@requires_procfs
def test_root_exit_one_with_remaining_descendant_is_detected(runner_temp, tmp_path):
    body = """
import os, sys, time, subprocess
subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
time.sleep(0.3)
sys.exit(1)
"""
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script_file(tmp_path, "attack4.py", body),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=30, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_DESCENDANT_SURVIVED_ROOT


@requires_procfs
def test_sigterm_ignoring_descendant_needs_sigkill(runner_temp, tmp_path):
    control = tmp_path / "pids.txt"
    body = f"""
import os, sys, time, signal
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    open({str(control)!r}, "a").write(str(os.getpid()) + "\\n")
    time.sleep(120)
    os._exit(0)
time.sleep(0.3)
sys.exit(0)
"""
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script_file(tmp_path, "attack7.py", body),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=30, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_DESCENDANT_SURVIVED_ROOT
    for pid in _read_pids(control, 1):
        assert not _pid_alive(pid), "SIGTERM 무시 후손이 SIGKILL 로도 안 죽었다"


# ══ timeout·출력 초과 + 후손 ═══════════════════════════════════════════
@requires_procfs
def test_timeout_kills_the_whole_process_group(runner_temp, tmp_path):
    control = tmp_path / "pids.txt"
    body = f"""
import os, sys, time, subprocess
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open({str(control)!r}, "a").write(str(p.pid) + "\\n")
time.sleep(120)
"""
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script_file(tmp_path, "attack5.py", body),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=2, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_TIMEOUT
    for pid in _read_pids(control, 1):
        assert not _pid_alive(pid), f"timeout 후 손자 {pid} 가 남았다"


@requires_procfs
def test_output_overflow_with_descendant_is_fail_closed(runner_temp, tmp_path):
    control = tmp_path / "pids.txt"
    body = f"""
import os, sys, time, subprocess
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open({str(control)!r}, "a").write(str(p.pid) + "\\n")
[sys.stdout.write("A" * 65536) for _ in iter(int, 1)]
"""
    started = time.monotonic()
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script_file(tmp_path, "attack6.py", body),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=120, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_OUTPUT_TOO_LARGE
    assert time.monotonic() - started < 60  # 실행 중 종료, timeout 을 기다리지 않는다
    for pid in _read_pids(control, 1):
        assert not _pid_alive(pid)


def test_stdout_overflow_is_fail_closed(runner_temp):
    body = "import sys" + chr(59) + " [sys.stdout.write('A'*65536) for _ in iter(int,1)]"
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script(body), cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=120, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_OUTPUT_TOO_LARGE


def test_limits_are_declared():
    assert oc.MAX_STDOUT_BYTES == 4 * 1024 * 1024
    assert oc.MAX_STDERR_BYTES == 4 * 1024 * 1024
    assert oc.MAX_TOTAL_BYTES == 8 * 1024 * 1024
    assert ls.GRACE_SECONDS > 0
    assert ls.TERM_WAIT_SECONDS > 0
    assert ls.KILL_WAIT_SECONDS > 0


def test_overflow_leaves_no_capture_behind(runner_temp):
    body = "import sys" + chr(59) + " [sys.stdout.write('A'*65536) for _ in iter(int,1)]"
    with pytest.raises(oc.ContainmentError):
        oc.run_contained(
            _script(body), cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=120, runner_temp=runner_temp,
        )
    assert list(runner_temp.iterdir()) == []


def test_timeout_leaves_no_capture_behind(runner_temp):
    with pytest.raises(oc.ContainmentError):
        oc.run_contained(
            _script("import time; time.sleep(60)"),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=1, runner_temp=runner_temp,
        )
    assert list(runner_temp.iterdir()) == []


# ══ zombie·grace·정상 상태 ═════════════════════════════════════════════
@requires_procfs
def test_zombie_child_is_reaped_not_counted_as_alive(runner_temp, tmp_path):
    body = """
import os, sys, time
pid = os.fork()
if pid == 0:
    os._exit(0)
time.sleep(0.3)   # parent 가 wait 하지 않아 zombie 가 된다
sys.exit(0)
"""
    result = oc.run_contained(
        _script_file(tmp_path, "zombie.py", body),
        cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=30, runner_temp=runner_temp,
    )
    assert result.returncode == 0
    assert result.cleanup_ok is True
    assert result.descendant_escape_detected is False
    assert result.process_group_empty is True


@requires_procfs
def test_descendant_that_exits_within_grace_is_success(runner_temp, tmp_path):
    body = """
import sys, subprocess, time
subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.15)"])
sys.exit(0)
"""
    result = oc.run_contained(
        _script_file(tmp_path, "grace.py", body),
        cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=30, runner_temp=runner_temp,
    )
    assert result.returncode == 0
    assert result.descendant_escape_detected is False
    assert result.cleanup_ok is True


def test_successful_command_returns_measured_metadata(runner_temp):
    result = oc.run_contained(
        _script("import sys; sys.stdout.write('hello'); sys.stderr.write('warn')"),
        cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=60, runner_temp=runner_temp,
    )
    assert result.returncode == 0
    assert result.stdout_bytes == 5
    assert result.stderr_bytes == 4
    assert result.cleanup_ok is True
    assert result.supervisor_children_empty is True


def test_run_and_read_cleans_up_after_itself(runner_temp):
    code, out, err = oc.run_and_read(
        _script("import sys; sys.stdout.write('x'); sys.stderr.write('y')"),
        cwd=REPO_ROOT, runner_temp=runner_temp,
    )
    assert (code, out, err) == (0, b"x", b"y")
    assert list(runner_temp.iterdir()) == []


def test_stdin_is_not_inherited(runner_temp):
    result = oc.run_contained(
        _script("import sys; sys.stdout.write(sys.stdin.read())"),
        cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=30, runner_temp=runner_temp,
    )
    assert result.stdout_bytes == 0


def test_stdin_file_is_supplied_when_requested(runner_temp, tmp_path):
    document = tmp_path / "document.bin"
    document.write_bytes(b"signed-bytes")
    code, out, _err = oc.run_and_read(
        _script("import sys; sys.stdout.write(sys.stdin.read())"),
        cwd=REPO_ROOT, runner_temp=runner_temp, stdin_path=document,
    )
    assert (code, out) == (0, b"signed-bytes")


# ══ §4-5 — 무관한 형제 프로세스는 살아남는다 ═══════════════════════════
@requires_procfs
def test_unrelated_sibling_process_survives(runner_temp):
    sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        result = oc.run_contained(
            _script("print('ok')"), cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=30, runner_temp=runner_temp,
        )
        assert result.returncode == 0
        time.sleep(0.3)
        assert _pid_alive(sibling.pid), "무관한 형제 프로세스를 죽였다 — 계약 위반"
    finally:
        sibling.kill()
        sibling.wait(timeout=5)


# ══ argv 계약 ══════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "argv",
    [[], "notalist", [""], ["git", "log\n"], ["git", "a\rb"], ["git", "a\x00b"], [1, 2]],
)
def test_invalid_argv_is_rejected(argv, runner_temp):
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            argv, cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=10, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_ARGV_INVALID


def test_argv_digest_is_stable_and_distinguishing():
    assert oc.argv_digest(["git", "log"]) == oc.argv_digest(["git", "log"])
    assert oc.argv_digest(["git", "log"]) != oc.argv_digest(["git", "diff"])


def test_spawn_failure_is_a_code(runner_temp):
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            ["/nonexistent/ac25/binary"], cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=10, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_SPAWN_FAILED


def test_missing_cwd_is_rejected(tmp_path, runner_temp):
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script("print(1)"), cwd=tmp_path / "absent", env=dict(os.environ),
            timeout_seconds=10, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_CWD_INVALID


def test_capture_root_must_exist(tmp_path):
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script("print(1)"), cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=10, runner_temp=tmp_path / "absent",
        )
    assert caught.value.code == oc.CONTAINMENT_CAPTURE_ROOT_INVALID


# ══ raw stdout/stderr capture 업로드 0건 ═══════════════════════════════
def test_workflow_uploads_only_approved_test_evidence():
    approved = {
        "ac25-junit.xml", "ac25-selftest.json", "ac25-publish.tap",
        "ac25-clean-status.porcelain-v2.z",
        "ac25-contract",
        "payload-manifest.json", "ac25-v44-contract", "ac25-evidence",
    }
    for path in WORKFLOWS:
        body = path.read_text(encoding="utf-8")
        assert "stdout.bin" not in body, path.name
        assert "stderr.bin" not in body, path.name
        if "upload-artifact" not in body:
            continue
        assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in body
        for line in body.splitlines():
            stripped = line.strip()
            if "runner.temp" in stripped and "/ac25-" in stripped:
                assert any(name in stripped for name in approved), stripped


def test_result_exposes_no_raw_text_fields():
    fields = set(oc.ContainedResult.__dataclass_fields__)
    assert "stdout_text" not in fields
    assert "stderr_text" not in fields
    assert "stdout_path" not in fields  # 경로조차 반환하지 않는다(R6-1)
    assert {"stdout_sha256", "stderr_sha256"} <= fields
    # §4-3 이 지정한 후손 관측 필드가 전부 있다
    assert {
        "descendants_observed", "descendants_terminated", "descendants_reaped",
        "descendant_escape_detected", "process_group_empty",
        "supervisor_children_empty", "raw_files_deleted", "cleanup_ok",
    } <= fields


def test_receipt_has_no_raw_and_no_path():
    result = oc.run_contained(
        _script("print('ok')"), cwd=REPO_ROOT, env=dict(os.environ),
        timeout_seconds=30, runner_temp=oc.default_runner_temp(),
    )
    receipt = result.as_receipt()
    for value in receipt.values():
        assert not isinstance(value, (list, dict))
    assert "stdout_path" not in receipt
    assert sys.executable not in str(receipt)
