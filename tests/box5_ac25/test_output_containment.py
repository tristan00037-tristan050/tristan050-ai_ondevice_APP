"""§5-7 C1 — 외부 process 공개 출력 격리 시험.

감사 C1: CLI 가 두 줄만 내도 자식이 부모 stream 을 상속하면 traceback·절대경로가
Actions log 로 직행한다. 그 CLI 가 부른 명령은 마음대로 뱉었다.

★가짜 실패 subprocess 를 실제로 돌려 부모 stdout·stderr 가 비어 있는지 본다.
★상한·timeout·프로세스 그룹 정리를 실제로 발동시킨다.
★production tree 를 AST 로 전수 조사해 격리기 밖 process 호출이 0 인지 본다.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from ac25 import output_containment as oc

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_DIR = REPO_ROOT / "scripts" / "ci" / "ac25"
CONTAINMENT = "output_containment.py"
WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("box5-ac25-*.yml"))

# 격리기 밖에서 쓰면 안 되는 이름
FORBIDDEN_MODULES = ("subprocess", "asyncio.subprocess")
FORBIDDEN_ATTRS = (
    "system", "popen", "execv", "execve", "execl", "execlp", "execvp",
    "posix_spawn", "posix_spawnp", "create_subprocess_exec", "create_subprocess_shell",
)

MARKER = "AC25_SECRET_MARKER_DO_NOT_LEAK"


def _other_modules() -> list[Path]:
    return [p for p in sorted(PRODUCTION_DIR.glob("*.py")) if p.name != CONTAINMENT]


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


def test_only_the_containment_module_names_subprocess():
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


def test_containment_module_disables_shell_explicitly():
    source = (PRODUCTION_DIR / CONTAINMENT).read_text(encoding="utf-8")
    assert "shell=False" in source
    assert "start_new_session=True" in source


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


# ══ 가짜 실패 subprocess — 부모 stream 에 아무것도 안 남는다 ═══════════
@pytest.fixture
def runner_temp(tmp_path) -> Path:
    root = tmp_path / "runner"
    root.mkdir()
    return root


def _script(body: str) -> list[str]:
    """argv 에 개행을 넣지 않는다(§5-3 2단계)."""
    return [sys.executable, "-c", body]


def test_child_traceback_never_reaches_the_parent(capfd, runner_temp):
    result = oc.run_contained(
        _script(f"raise RuntimeError('{MARKER}')"),
        cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=60, runner_temp=runner_temp,
    )
    try:
        captured = capfd.readouterr()
        assert MARKER not in captured.out
        assert MARKER not in captured.err
        assert captured.out == ""
        assert captured.err == ""
        # 그래도 자식은 실제로 실패했고 그 사실은 남는다
        assert result.returncode != 0
        assert result.stderr_bytes_observed > 0
        assert MARKER.encode() in oc.read_capture(result.stderr_path, limit=1 << 20)
    finally:
        oc.discard(result)


def test_absolute_paths_never_reach_the_parent(capfd, runner_temp):
    result = oc.run_contained(
        _script("import sys; sys.stderr.write('/etc/passwd /Users/secret/token')"),
        cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=60, runner_temp=runner_temp,
    )
    try:
        captured = capfd.readouterr()
        assert "/etc/passwd" not in captured.err
        assert "/Users/secret" not in captured.err
    finally:
        oc.discard(result)


def test_error_message_carries_only_a_code(runner_temp):
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script("import time; time.sleep(60)"),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=1,
            runner_temp=runner_temp,
        )
    message = str(caught.value)
    assert message == oc.CONTAINMENT_TIMEOUT
    assert "/" not in message
    assert MARKER not in message


# ══ 상한 — 실행 중 강제 ════════════════════════════════════════════════
def test_stdout_overflow_is_fail_closed(runner_temp):
    body = "import sys" + chr(59) + " [sys.stdout.write('A'*65536) for _ in iter(int,1)]"
    started = time.monotonic()
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script(body), cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=120, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_OUTPUT_TOO_LARGE
    # ★사후 절단이 아니라 실행 중 종료다 — timeout 을 기다리지 않는다
    assert time.monotonic() - started < 60


def test_stderr_overflow_is_fail_closed(runner_temp):
    body = "import sys" + chr(59) + " [sys.stderr.write('B'*65536) for _ in iter(int,1)]"
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
    assert oc.TERMINATE_GRACE_SECONDS == 3


def test_overflow_leaves_no_capture_behind(runner_temp):
    body = "import sys" + chr(59) + " [sys.stdout.write('A'*65536) for _ in iter(int,1)]"
    with pytest.raises(oc.ContainmentError):
        oc.run_contained(
            _script(body), cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=120, runner_temp=runner_temp,
        )
    assert list(runner_temp.iterdir()) == []


# ══ timeout 과 프로세스 그룹 ═══════════════════════════════════════════
def test_timeout_kills_the_whole_process_group(runner_temp):
    marker = "AC25_GRANDCHILD_MARKER"
    body = (
        "import subprocess,sys,time" + chr(59) +
        f" subprocess.Popen([sys.executable,'-c','import time{chr(59)} time.sleep(90)'])"
        + chr(59) + " time.sleep(90)"
    )
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script(body), cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=2, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_TIMEOUT
    time.sleep(0.5)
    # ★손자가 남지 않는다
    survivors = subprocess.run(
        ["pgrep", "-f", "time.sleep(90)"], capture_output=True, text=True, check=False
    ).stdout.split()
    assert survivors == [], survivors
    assert marker not in "".join(survivors)


def test_timeout_leaves_no_capture_behind(runner_temp):
    with pytest.raises(oc.ContainmentError):
        oc.run_contained(
            _script("import time; time.sleep(60)"),
            cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=1,
            runner_temp=runner_temp,
        )
    assert list(runner_temp.iterdir()) == []


# ══ capture 위치와 권한 ════════════════════════════════════════════════
def test_capture_directory_and_files_are_private(runner_temp):
    result = oc.run_contained(
        _script("print('ok')"), cwd=REPO_ROOT, env=dict(os.environ),
        timeout_seconds=60, runner_temp=runner_temp,
    )
    try:
        assert oct(result.stdout_path.parent.stat().st_mode & 0o777) == "0o700"
        assert oct(result.stdout_path.stat().st_mode & 0o777) == "0o600"
        assert oct(result.stderr_path.stat().st_mode & 0o777) == "0o600"
        assert result.stdout_path.parent.parent == runner_temp.resolve()
    finally:
        oc.discard(result)


def test_capture_root_must_exist(tmp_path):
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script("print(1)"), cwd=REPO_ROOT, env=dict(os.environ),
            timeout_seconds=10, runner_temp=tmp_path / "absent",
        )
    assert caught.value.code == oc.CONTAINMENT_CAPTURE_ROOT_INVALID


def test_capture_root_symlink_escape_is_resolved(tmp_path, runner_temp):
    """symlink 는 resolve(strict=True) 로 실제 위치가 된다."""
    link = tmp_path / "link"
    link.symlink_to(runner_temp)
    result = oc.run_contained(
        _script("print(1)"), cwd=REPO_ROOT, env=dict(os.environ),
        timeout_seconds=30, runner_temp=link,
    )
    try:
        assert result.stdout_path.parent.parent == runner_temp.resolve()
    finally:
        oc.discard(result)


def test_missing_cwd_is_rejected(tmp_path, runner_temp):
    with pytest.raises(oc.ContainmentError) as caught:
        oc.run_contained(
            _script("print(1)"), cwd=tmp_path / "absent", env=dict(os.environ),
            timeout_seconds=10, runner_temp=runner_temp,
        )
    assert caught.value.code == oc.CONTAINMENT_CWD_INVALID


def test_discard_removes_the_capture_directory(runner_temp):
    result = oc.run_contained(
        _script("print(1)"), cwd=REPO_ROOT, env=dict(os.environ),
        timeout_seconds=30, runner_temp=runner_temp,
    )
    directory = result.stdout_path.parent
    oc.discard(result)
    assert not directory.exists()


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


def test_argv_is_recorded_only_as_a_digest(runner_temp):
    result = oc.run_contained(
        _script("print(1)"), cwd=REPO_ROOT, env=dict(os.environ),
        timeout_seconds=30, runner_temp=runner_temp,
    )
    try:
        receipt = result.as_receipt()
        assert len(receipt["argv_sha256"]) == 64
        assert "argv" not in receipt
        for value in receipt.values():
            assert not isinstance(value, (list, dict))
        assert sys.executable not in str(receipt)
    finally:
        oc.discard(result)


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


# ══ 정상 상태 — 언제나 막는 격리기는 합격이 아니다 ═════════════════════
def test_successful_command_returns_measured_metadata(runner_temp):
    result = oc.run_contained(
        _script("import sys; sys.stdout.write('hello'); sys.stderr.write('warn')"),
        cwd=REPO_ROOT, env=dict(os.environ), timeout_seconds=60, runner_temp=runner_temp,
    )
    try:
        assert result.returncode == 0
        assert result.stdout_bytes_observed == 5
        assert result.stderr_bytes_observed == 4
        assert result.truncated is False
        assert oc.read_capture(result.stdout_path, limit=100) == b"hello"
    finally:
        oc.discard(result)


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
    try:
        assert result.stdout_bytes_observed == 0
    finally:
        oc.discard(result)


def test_stdin_file_is_supplied_when_requested(runner_temp, tmp_path):
    document = tmp_path / "document.bin"
    document.write_bytes(b"signed-bytes")
    code, out, _err = oc.run_and_read(
        _script("import sys; sys.stdout.write(sys.stdin.read())"),
        cwd=REPO_ROOT, runner_temp=runner_temp, stdin_path=document,
    )
    assert (code, out) == (0, b"signed-bytes")


# ══ raw artifact 업로드 0건 ════════════════════════════════════════════
def test_no_workflow_uploads_raw_captures():
    """★raw stdout·stderr artifact 업로드를 금지한다(§5-1).

    공개 저장소에서 artifact 는 저장소 read 권한이면 누구나 받는다.
    """
    for path in WORKFLOWS:
        body = path.read_text(encoding="utf-8")
        assert "upload-artifact" not in body, path.name
        assert "stdout_path" not in body, path.name
        assert "stderr_path" not in body, path.name
        assert "stdout.bin" not in body, path.name
        assert "stderr.bin" not in body, path.name


def test_receipt_helper_exposes_no_raw_fields():
    fields = set(oc.ContainedResult.__dataclass_fields__)
    assert "stdout_text" not in fields
    assert "stderr_text" not in fields
    assert {"stdout_sha256", "stderr_sha256"} <= fields
