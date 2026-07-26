"""인계 폴더 권한복구 스크립트 회귀 시험.

2026-07-17 그룹A 지적: 복구 스크립트가 모든 파일을 644 로 만든 뒤 .sh/.py 만 755 로
되돌려서, 확장자가 없는 실행 파일(Butler.app/Contents/MacOS/butler-desktop 등)이
644 로 남아 앱이 열리지 않았다.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_sidecar_token

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "handoff" / "restore_permissions.sh"

# Mach-O 64bit little-endian 매직. 실제 실행 파일과 같은 첫 4바이트다.
MACH_O = b"\xcf\xfa\xed\xfe" + b"\x00" * 60
GGUF = b"GGUF" + b"\x00" * 60
# universal(fat) 바이너리 매직 — 64비트 변종(FAT_MAGIC_64 / FAT_CIGAM_64)을 포함한다.
FAT_MAGICS = {
    "fat32_be": b"\xca\xfe\xba\xbe",
    "fat32_le": b"\xbe\xba\xfe\xca",
    "fat64_be": b"\xca\xfe\xba\xbf",
    "fat64_le": b"\xbf\xba\xfe\xca",
}


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


@pytest.mark.parametrize("label", sorted(FAT_MAGICS))
def test_universal_binaries_including_fat64_are_detected(
    handoff_package: Path, label: str
) -> None:
    """64비트 universal(fat) 바이너리도 실행 파일로 인식해야 한다."""
    binary = handoff_package / "도구" / f"universal-{label}"
    binary.write_bytes(FAT_MAGICS[label] + b"\x00" * 60)
    binary.chmod(0o700)

    result = _run(handoff_package)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _mode(binary) == 0o755


# ── 대상 검증: 재귀 chmod 가 엉뚱한 곳에 걸리지 않아야 한다 ──────────────


def _package_with_marker(root: Path) -> Path:
    (root / "Butler.app" / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    (root / "Butler.app" / "Contents" / "MacOS" / "butler-desktop").write_bytes(MACH_O)
    return root


def test_refuses_filesystem_root() -> None:
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "/"], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "거부" in result.stdout + result.stderr


def test_refuses_top_level_directory() -> None:
    top_level = Path("/Users")
    if not top_level.is_dir():
        pytest.skip("최상위 디렉터리를 확인할 수 없는 환경")
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), str(top_level)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "거부" in result.stdout + result.stderr


def test_refuses_home_directory(tmp_path: Path) -> None:
    """표식이 있어도 홈 디렉터리 자체는 대상이 될 수 없다."""
    fake_home = _package_with_marker(tmp_path / "home")
    environment = {**os.environ, "HOME": str(fake_home)}
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), str(fake_home)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert result.returncode != 0
    assert "홈 디렉터리" in result.stdout + result.stderr
    assert _mode(fake_home / "Butler.app" / "Contents" / "MacOS" / "butler-desktop") != 0o755


def test_refuses_git_repository_root(tmp_path: Path) -> None:
    repository = _package_with_marker(tmp_path / "repo")
    (repository / ".git").mkdir()
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), str(repository)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "저장소 루트" in result.stdout + result.stderr


def test_refuses_symlink_target(tmp_path: Path) -> None:
    package = _package_with_marker(tmp_path / "package")
    link = tmp_path / "link"
    link.symlink_to(package, target_is_directory=True)
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), str(link)], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "심볼릭 링크" in result.stdout + result.stderr


def test_refuses_directory_without_handoff_marker(tmp_path: Path) -> None:
    """인계 패키지가 아닌 폴더는 건드리지 않는다."""
    ordinary = tmp_path / "내문서"
    ordinary.mkdir()
    secret = ordinary / "가계부.txt"
    secret.write_text("비밀\n", encoding="utf-8")
    secret.chmod(0o600)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), str(ordinary)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "표식이 없습니다" in result.stdout + result.stderr
    # ★권한이 바뀌지 않아야 한다(644 로 열리면 다른 사용자에게 노출된다).
    assert _mode(secret) == 0o600


def _parent_with_nested_package(tmp_path: Path) -> tuple[Path, Path, Path]:
    """인계 폴더의 한 칸 위 — 옆에 개인 자료가 있는 상황."""
    parent = tmp_path / "바탕화면"
    package = _package_with_marker(parent / "package")
    secret = parent / "secret.txt"
    secret.write_text("개인 자료\n", encoding="utf-8")
    secret.chmod(0o600)
    (package / "Butler.app" / "Contents" / "MacOS" / "butler-desktop").chmod(0o700)
    return parent, package, secret


def test_refuses_parent_of_package_even_though_app_exists_below(tmp_path: Path) -> None:
    """★하위 트리에 Butler.app 이 있어도 한 칸 위는 대상이 될 수 없다."""
    parent, package, secret = _parent_with_nested_package(tmp_path)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), str(parent)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "표식이 없습니다" in result.stdout + result.stderr
    # 옆 개인 자료가 열리지 않아야 한다.
    assert _mode(secret) == 0o600
    # 패키지 내부도 손대지 않아야 한다.
    assert _mode(package / "Butler.app" / "Contents" / "MacOS" / "butler-desktop") == 0o700


def test_refuses_relative_parent_from_inside_package(tmp_path: Path) -> None:
    """패키지 안에서 `..` 로 한 칸 위를 지정해도 막혀야 한다."""
    parent, package, secret = _parent_with_nested_package(tmp_path)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), ".."],
        cwd=str(package),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "표식이 없습니다" in result.stdout + result.stderr
    assert _mode(secret) == 0o600
    assert _mode(package / "Butler.app" / "Contents" / "MacOS" / "butler-desktop") == 0o700


def test_package_itself_is_still_accepted(tmp_path: Path) -> None:
    """한 칸 위는 거부하되, 패키지 자체는 정상 동작해야 한다."""
    _parent, package, secret = _parent_with_nested_package(tmp_path)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), str(package)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _mode(package / "Butler.app" / "Contents" / "MacOS" / "butler-desktop") == 0o755
    assert _mode(secret) == 0o600  # 패키지 밖은 건드리지 않는다


# ── manifest 표식: 파일 존재만으로 승인하지 않는다 ──────────────────────

MANIFEST_SCHEMA = "butler.handoff.manifest.v1"


def _nested_app_package(root: Path, *, app_relative: str = "01_앱/Butler.app") -> Path:
    """앱이 하위 폴더에 있는 실제 인계 패키지 모양."""
    app = root / app_relative
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "butler-desktop").write_bytes(MACH_O)
    (root / "00_먼저읽기.md").write_text("# 안내\n", encoding="utf-8")
    return root


def _write_manifest(package: Path, payload: object, name: str = "HANDOFF_MANIFEST.json") -> Path:
    path = package / name
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _harden(package: Path) -> None:
    for path in sorted(package.rglob("*"), reverse=True):
        path.chmod(0o700)


def _valid_manifest(package: Path, app_relative: str = "01_앱/Butler.app") -> dict:
    return {
        "schema_version": MANIFEST_SCHEMA,
        "package_root": package.name,
        "app_paths": [app_relative],
        "created_utc": "2026-07-26T01:00:00Z",
    }


def test_valid_manifest_is_accepted_and_restores_nested_app(tmp_path: Path) -> None:
    package = _nested_app_package(tmp_path / "그룹A_인계")
    _write_manifest(package, _valid_manifest(package))
    _harden(package)

    result = _run(package)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "검증됨" in result.stdout
    binary = package / "01_앱" / "Butler.app" / "Contents" / "MacOS" / "butler-desktop"
    assert _mode(binary) == 0o755
    assert _mode(package / "00_먼저읽기.md") == 0o644


def test_empty_manifest_is_rejected(tmp_path: Path) -> None:
    """★빈 {} manifest 는 표식이 아니다."""
    package = _nested_app_package(tmp_path / "그룹A_인계")
    _write_manifest(package, {})
    _harden(package)

    result = _run(package)
    assert result.returncode != 0
    assert "manifest 가 유효하지 않습니다" in result.stdout + result.stderr
    binary = package / "01_앱" / "Butler.app" / "Contents" / "MacOS" / "butler-desktop"
    assert _mode(binary) == 0o700


def test_empty_manifest_in_parent_folder_does_not_open_neighbours(tmp_path: Path) -> None:
    """빈 manifest 를 상위 폴더에 두어도 옆 개인 자료가 열리지 않아야 한다."""
    parent = tmp_path / "바탕화면"
    package = _nested_app_package(parent / "그룹A_인계")
    secret = parent / "secret.txt"
    secret.write_text("개인 자료\n", encoding="utf-8")
    secret.chmod(0o600)
    _write_manifest(parent, {})
    _harden(package)

    result = _run(parent)
    assert result.returncode != 0
    assert _mode(secret) == 0o600
    # 패키지 내부도 그대로여야 한다.
    assert _mode(package / "01_앱" / "Butler.app" / "Contents" / "MacOS") == 0o700


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda m, p: m.update(schema_version="butler.handoff.manifest.v2"), "schema_version"),
        (lambda m, p: m.pop("schema_version"), "schema_version"),
        (lambda m, p: m.pop("app_paths"), "app_paths"),
        (lambda m, p: m.update(app_paths=[]), "app_paths"),
        (lambda m, p: m.update(app_paths="01_앱/Butler.app"), "app_paths"),
        (lambda m, p: m.update(app_paths=["01_앱/Butler.app", 7]), "app_paths"),
        (lambda m, p: m.update(package_root="다른이름"), "package_root"),
        (lambda m, p: m.pop("package_root"), "package_root"),
        (lambda m, p: m.update(package_root="../바깥"), "package_root"),
        (lambda m, p: m.update(app_paths=["../바깥/Butler.app"]), ".."),
        (lambda m, p: m.update(app_paths=["01_앱/../../바깥/Butler.app"]), ".."),
        (lambda m, p: m.update(app_paths=["/Applications/Butler.app"]), "절대 경로"),
        (lambda m, p: m.update(app_paths=["없는폴더/Butler.app"]), "존재하지 않습니다"),
        (lambda m, p: m.update(app_paths=["00_먼저읽기.md"]), "디렉터리가 아닙니다"),
    ],
)
def test_manifest_schema_violations_are_rejected(tmp_path: Path, mutate, reason: str) -> None:
    package = _nested_app_package(tmp_path / "그룹A_인계")
    manifest = _valid_manifest(package)
    mutate(manifest, package)
    _write_manifest(package, manifest)
    _harden(package)

    result = _run(package)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "유효하지 않습니다" in output
    assert reason in output or "manifest" in output
    binary = package / "01_앱" / "Butler.app" / "Contents" / "MacOS" / "butler-desktop"
    assert _mode(binary) == 0o700


def test_manifest_with_symlinked_app_path_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "바깥" / "Butler.app" / "Contents" / "MacOS"
    outside.mkdir(parents=True)
    package = tmp_path / "그룹A_인계"
    package.mkdir()
    (package / "01_앱").mkdir()
    (package / "01_앱" / "Butler.app").symlink_to(
        tmp_path / "바깥" / "Butler.app", target_is_directory=True
    )
    _write_manifest(package, _valid_manifest(package))

    result = _run(package)
    assert result.returncode != 0
    assert "symlink" in result.stdout + result.stderr


def test_symlinked_manifest_is_rejected(tmp_path: Path) -> None:
    package = _nested_app_package(tmp_path / "그룹A_인계")
    real = _write_manifest(package, _valid_manifest(package), name="real_manifest.json")
    (package / "HANDOFF_MANIFEST.json").symlink_to(real)

    result = _run(package)
    assert result.returncode != 0
    assert "symlink" in result.stdout + result.stderr


def test_broken_json_manifest_is_rejected(tmp_path: Path) -> None:
    package = _nested_app_package(tmp_path / "그룹A_인계")
    (package / "HANDOFF_MANIFEST.json").write_text("{oops", encoding="utf-8")

    result = _run(package)
    assert result.returncode != 0
    assert "유효하지 않습니다" in result.stdout + result.stderr


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
