"""인계 폴더 권한복구 스크립트 회귀 시험.

2026-07-17 그룹A 지적: 복구 스크립트가 모든 파일을 644 로 만든 뒤 .sh/.py 만 755 로
되돌려서, 확장자가 없는 실행 파일(Butler.app/Contents/MacOS/butler-desktop 등)이
644 로 남아 앱이 열리지 않았다.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_sidecar_token

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "handoff" / "restore_permissions.sh"

# Mach-O 64bit little-endian 매직. 실제 실행 파일과 같은 첫 4바이트다.
MACH_O = b"\xcf\xfa\xed\xfe" + b"\x00" * 60
GGUF = b"GGUF" + b"\x00" * 60


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


@pytest.fixture()
def handoff_package(tmp_path: Path) -> Path:
    """T7(exFAT)에서 내장 디스크로 막 복사된 직후 상태를 재현한다 — 전부 700."""
    package = tmp_path / "그룹A_인계"
    app_macos = package / "Butler.app" / "Contents" / "MacOS"
    app_bin = package / "Butler.app" / "Contents" / "Resources" / "python" / "bin"
    frameworks = package / "Butler.app" / "Contents" / "Frameworks"
    for directory in (app_macos, app_bin, frameworks, package / "docs"):
        directory.mkdir(parents=True, exist_ok=True)

    # 확장자 없는 실행 파일 — 이번 버그의 대상
    (app_macos / "butler-desktop").write_bytes(MACH_O)
    (app_macos / "butler-sidecar").write_bytes(b"#!/bin/sh\nexec true\n")
    (app_bin / "python3").write_bytes(MACH_O)
    # 확장자 있는 실행 파일
    (package / "run.sh").write_text("#!/bin/bash\ntrue\n", encoding="utf-8")
    (package / "tool.py").write_text("print('x')\n", encoding="utf-8")
    (frameworks / "libbutler.dylib").write_bytes(MACH_O)
    # 표준 실행 경로 밖에 놓인 확장자 없는 실행 파일 — 내용으로만 판별된다
    tools = package / "도구"
    tools.mkdir(parents=True, exist_ok=True)
    (tools / "butler-verify").write_bytes(MACH_O)
    (tools / "butler-check").write_bytes(b"#!/bin/sh\nexec true\n")
    # 실행 파일이 아닌 것 — 644 로 남아야 한다
    (package / "docs" / "00_먼저읽기.md").write_text("# 안내\n", encoding="utf-8")
    (package / "docs" / "notes.txt").write_text("메모\n", encoding="utf-8")
    (package / "model.gguf").write_bytes(GGUF)

    for path in sorted(package.rglob("*"), reverse=True):
        path.chmod(0o700)
    package.chmod(0o700)
    return package


def _run(package: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), str(package)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_extensionless_executables_stay_executable(handoff_package: Path) -> None:
    """★회귀 지점: 확장자 없는 실행 파일이 644 로 죽지 않아야 한다."""
    result = _run(handoff_package)
    assert result.returncode == 0, result.stdout + result.stderr

    macos = handoff_package / "Butler.app" / "Contents" / "MacOS"
    assert _mode(macos / "butler-desktop") == 0o755
    assert _mode(macos / "butler-sidecar") == 0o755
    python_binary = (
        handoff_package / "Butler.app" / "Contents" / "Resources" / "python" / "bin" / "python3"
    )
    assert _mode(python_binary) == 0o755


def test_executables_outside_standard_paths_are_detected_by_content(
    handoff_package: Path,
) -> None:
    """MacOS/·bin/ 밖에 있어도 내용(Mach-O·shebang)으로 판별해 되살린다."""
    result = _run(handoff_package)
    assert result.returncode == 0, result.stdout + result.stderr

    assert _mode(handoff_package / "도구" / "butler-verify") == 0o755
    assert _mode(handoff_package / "도구" / "butler-check") == 0o755


def test_documents_are_readable_not_executable(handoff_package: Path) -> None:
    result = _run(handoff_package)
    assert result.returncode == 0, result.stdout + result.stderr

    assert _mode(handoff_package / "docs" / "00_먼저읽기.md") == 0o644
    assert _mode(handoff_package / "docs" / "notes.txt") == 0o644
    # 모델 가중치는 실행 파일이 아니다.
    assert _mode(handoff_package / "model.gguf") == 0o644


def test_scripts_and_directories_get_expected_modes(handoff_package: Path) -> None:
    result = _run(handoff_package)
    assert result.returncode == 0, result.stdout + result.stderr

    assert _mode(handoff_package / "run.sh") == 0o755
    assert _mode(handoff_package / "tool.py") == 0o755
    assert _mode(handoff_package / "docs") == 0o755
    assert _mode(handoff_package / "Butler.app" / "Contents" / "MacOS") == 0o755


def test_restored_executable_actually_runs(handoff_package: Path) -> None:
    """권한만 맞추는 게 아니라 실제로 실행되는지까지 본다."""
    result = _run(handoff_package)
    assert result.returncode == 0, result.stdout + result.stderr

    sidecar = handoff_package / "Butler.app" / "Contents" / "MacOS" / "butler-sidecar"
    assert subprocess.run([str(sidecar)], check=False).returncode == 0


def test_old_extension_only_rule_would_have_failed(handoff_package: Path) -> None:
    """예전 규칙(.sh/.py 만 755)을 그대로 재현하면 앱 실행부가 644 로 죽는다."""
    subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -e; d="$1"; '
            'find "$d" -type d -exec chmod 755 {} +; '
            'find "$d" -type f -exec chmod 644 {} +; '
            "find \"$d\" -type f -name '*.sh' -exec chmod 755 {} +; "
            "find \"$d\" -type f -name '*.py' -exec chmod 755 {} +",
            "_",
            str(handoff_package),
        ],
        check=True,
    )
    macos = handoff_package / "Butler.app" / "Contents" / "MacOS"
    assert _mode(macos / "butler-desktop") == 0o644  # 버그 재현

    # 수정본을 돌리면 되살아난다.
    assert _run(handoff_package).returncode == 0
    assert _mode(macos / "butler-desktop") == 0o755


def test_self_check_reports_unrecovered_app_binary(tmp_path: Path) -> None:
    """실행부를 못 살렸다면 조용히 성공하지 않고 실패로 알린다."""
    package = tmp_path / "pkg"
    macos = package / "Butler.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    # 실행 파일이 아닌 잡음 파일을 MacOS 아래 두면 경로 규칙으로 755 가 된다.
    (macos / "butler-desktop").write_bytes(MACH_O)
    result = _run(package)
    assert result.returncode == 0
    assert _mode(macos / "butler-desktop") == 0o755
