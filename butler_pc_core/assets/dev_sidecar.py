from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import stat
import struct
import subprocess
import sys
from pathlib import Path

from .context import MAX_BOOTSTRAP_BYTES

_BOOTSTRAP_FD_ENV = "BUTLER_BOOTSTRAP_FD"
_LISTEN_FD_ENV = "BUTLER_LISTEN_FD"
_APP_DATA_ENV = "BUTLER_APP_DATA_DIR"
_DEFAULT_MODE = 0o700


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Butler sidecar with a development-only descriptor bootstrap."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--app-data", type=Path)
    parser.add_argument("--listen-fd", type=int, help=argparse.SUPPRESS)
    return parser


def _default_app_data() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ButlerDev"
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        path = Path(data_home)
        if not path.is_absolute():
            raise SystemExit("BLOCK_DEVELOPMENT_APP_DATA_INVALID")
        return path / "butler-dev"
    return Path.home() / ".local" / "share" / "butler-dev"


def _private_directory(path: Path) -> Path:
    if not path.is_absolute():
        raise SystemExit("BLOCK_DEVELOPMENT_APP_DATA_INVALID")
    try:
        path.mkdir(mode=_DEFAULT_MODE, parents=True, exist_ok=True)
        info = path.lstat()
    except OSError as exc:
        raise SystemExit("BLOCK_DEVELOPMENT_APP_DATA_UNAVAILABLE") from exc
    if (
        path.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_mode & 0o022
        or (hasattr(os, "getuid") and info.st_uid != os.getuid())
    ):
        raise SystemExit("BLOCK_DEVELOPMENT_APP_DATA_UNSAFE")
    return path


def _open_development_asset_root(app_data: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    app_data_fd = os.open(app_data, flags)
    try:
        try:
            os.mkdir(
                "development-assets",
                mode=_DEFAULT_MODE,
                dir_fd=app_data_fd,
            )
        except FileExistsError:
            pass
        asset_fd = os.open("development-assets", flags, dir_fd=app_data_fd)
    finally:
        os.close(app_data_fd)
    try:
        info = os.fstat(asset_fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_mode & 0o022
            or (hasattr(os, "getuid") and info.st_uid != os.getuid())
        ):
            raise SystemExit("BLOCK_DEVELOPMENT_ASSET_ROOT_UNSAFE")
        return asset_fd
    except BaseException:
        os.close(asset_fd)
        raise


def _listener_address(host: str, port: int) -> tuple[int, tuple[object, ...]]:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise SystemExit("BLOCK_DEVELOPMENT_LISTEN_ADDRESS_INVALID") from exc
    if not address.is_loopback:
        raise SystemExit("BLOCK_DEVELOPMENT_LISTEN_ADDRESS_INVALID")
    family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
    return family, (str(address), port)


def _validate_listener(descriptor: int, *, host: str, port: int) -> None:
    if descriptor < 0:
        raise SystemExit("BLOCK_DEVELOPMENT_LISTENER_INVALID")
    family, expected = _listener_address(host, port)
    try:
        candidate = socket.socket(fileno=os.dup(descriptor))
        try:
            if (
                candidate.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
                != socket.SOCK_STREAM
                or candidate.family != family
            ):
                raise SystemExit("BLOCK_DEVELOPMENT_LISTENER_INVALID")
            bound = candidate.getsockname()
            if bound[0] != expected[0] or bound[1] != expected[1]:
                raise SystemExit("BLOCK_DEVELOPMENT_LISTENER_MISMATCH")
        finally:
            candidate.close()
    except OSError as exc:
        raise SystemExit("BLOCK_DEVELOPMENT_LISTENER_INVALID") from exc


def _open_listener(*, host: str, port: int) -> int:
    family, address = _listener_address(host, port)
    listener = socket.socket(family, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(address)
        listener.listen(2048)
        listener.set_inheritable(True)
        return listener.detach()
    except OSError as exc:
        listener.close()
        raise SystemExit("BLOCK_DEVELOPMENT_LISTENER_UNAVAILABLE") from exc


def _git_oid(repository_root: Path, revision: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", revision],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    value = completed.stdout.strip()
    if (
        completed.returncode != 0
        or len(value) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in value)
        or value == "0" * len(value)
    ):
        raise SystemExit("BLOCK_DEVELOPMENT_SOURCE_IDENTITY")
    return value


def _bootstrap_frame(
    *,
    app_data: Path,
    asset_root_fd: int,
    repository_root: Path,
) -> bytes:
    commit = _git_oid(repository_root, "HEAD^{commit}")
    tree = _git_oid(repository_root, "HEAD^{tree}")
    payload = {
        "schema_version": 1,
        "asset_root_fd": asset_root_fd,
        "app_data_root": str(app_data),
        "release_profile": "development",
        "build_id": commit,
        "source_commit": commit,
        "source_tree": tree,
        "manifest_set_sha256": None,
        "trust_root_status": "TRUST_ROOT_NOT_CONFIGURED",
        "root_policy_sha256": None,
        "trusted_keys": [],
        "trust_epoch": None,
        "revoked_key_ids": [],
        "security_state": {
            "byte_safety_verified": False,
            "origin_verified": False,
            "trust_root_state": "UNCONFIGURED",
            "signature_state": "MISSING",
            "provenance_state": "UNVERIFIED",
            "release_ready": False,
            "external_handoff_allowed": 0,
            "auto_update_allowed": 0,
            "operation_scope": "INTERNAL_OWNER_ONLY",
        },
    }
    raw = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if not 1 <= len(raw) <= MAX_BOOTSTRAP_BYTES:
        raise SystemExit("BLOCK_DEVELOPMENT_BOOTSTRAP_INVALID")
    return struct.pack(">I", len(raw)) + raw


def _child_environment(
    *,
    app_data: Path,
    bootstrap_fd: int,
    listener_fd: int | None = None,
) -> dict[str, str]:
    # macOS Keychain lookup is bound to the real login home. Other POSIX
    # development runtimes keep every home-relative write inside the private
    # app-data authority instead of inheriting an absent or shared CI HOME.
    home = (
        os.environ.get("HOME", str(Path.home()))
        if sys.platform == "darwin"
        else str(app_data)
    )
    environment: dict[str, str] = {
        _APP_DATA_ENV: str(app_data),
        _BOOTSTRAP_FD_ENV: str(bootstrap_fd),
        "BUTLER_PRODUCTION": "0",
        "HOME": home,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "PATH": os.environ.get("PATH", os.defpath),
    }
    if listener_fd is not None:
        environment[_LISTEN_FD_ENV] = str(listener_fd)
    for name in ("TMPDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    if os.environ.get("BUTLER_HOME_BOOTSTRAP_NEW_INSTALL") == "1":
        environment["BUTLER_HOME_BOOTSTRAP_NEW_INSTALL"] = "1"
    return environment


def main() -> int:
    if os.name != "posix" or not all(
        hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
    ):
        raise SystemExit("BLOCK_DEVELOPMENT_LAUNCHER_PLATFORM_UNSUPPORTED")
    arguments = _parser().parse_args()
    if not 1 <= arguments.port <= 65535 or "\x00" in arguments.host:
        raise SystemExit("BLOCK_DEVELOPMENT_LISTEN_ADDRESS_INVALID")
    raw_app_data = arguments.app_data
    if raw_app_data is None:
        configured = os.environ.get(_APP_DATA_ENV)
        raw_app_data = Path(configured) if configured else _default_app_data()
    app_data = _private_directory(raw_app_data)
    repository_root = Path(__file__).absolute().parents[2]
    sidecar = repository_root / "butler_sidecar.py"
    if not sidecar.is_file() or sidecar.is_symlink():
        raise SystemExit("BLOCK_DEVELOPMENT_SIDECAR_UNAVAILABLE")

    listener_fd = -1
    asset_root_fd = -1
    read_fd = -1
    write_fd = -1
    try:
        if arguments.listen_fd is None:
            listener_fd = _open_listener(
                host=arguments.host,
                port=arguments.port,
            )
        else:
            listener_fd = arguments.listen_fd
            _validate_listener(
                listener_fd,
                host=arguments.host,
                port=arguments.port,
            )
            os.set_inheritable(listener_fd, True)
        asset_root_fd = _open_development_asset_root(app_data)
        read_fd, write_fd = os.pipe()
        frame = _bootstrap_frame(
            app_data=app_data,
            asset_root_fd=asset_root_fd,
            repository_root=repository_root,
        )
        with os.fdopen(write_fd, "wb", closefd=True) as stream:
            write_fd = -1
            stream.write(frame)
        os.set_inheritable(read_fd, True)
        os.set_inheritable(asset_root_fd, True)
        environment = _child_environment(
            app_data=app_data,
            bootstrap_fd=read_fd,
            listener_fd=listener_fd,
        )
        os.execve(
            sys.executable,
            [
                sys.executable,
                str(sidecar),
                "--host",
                arguments.host,
                "--port",
                str(arguments.port),
            ],
            environment,
        )
    finally:
        if write_fd >= 0:
            os.close(write_fd)
        if read_fd >= 0:
            os.close(read_fd)
        if asset_root_fd >= 0:
            os.close(asset_root_fd)
        if listener_fd >= 0:
            os.close(listener_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
