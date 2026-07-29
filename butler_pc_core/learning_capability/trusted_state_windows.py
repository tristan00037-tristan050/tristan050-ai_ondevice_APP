from __future__ import annotations

import ctypes
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Final


class WindowsTrustedStateError(RuntimeError):
    pass


_RESERVED: Final = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_BROAD_WRITE_MASK: Final = (
    0x0002  # FILE_WRITE_DATA
    | 0x0004  # FILE_APPEND_DATA
    | 0x0010  # FILE_WRITE_EA
    | 0x0100  # FILE_WRITE_ATTRIBUTES
    | 0x00010000  # DELETE
    | 0x00040000  # WRITE_DAC
    | 0x00080000  # WRITE_OWNER
  )


def validate_relative_name(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith(("\\\\", "/", "\\?\\", "\\.\\"))
        or "/" in value
        or "\\" in value
        or ":" in value
        or value.endswith((" ", "."))
    ):
        raise WindowsTrustedStateError("WINDOWS_NAMESPACE_REJECTED")
    path = PureWindowsPath(value)
    if path.is_absolute() or path.drive or len(path.parts) != 1:
        raise WindowsTrustedStateError("WINDOWS_NAMESPACE_REJECTED")
    if value in {".", ".."} or value.split(".", 1)[0].upper() in _RESERVED:
        raise WindowsTrustedStateError("WINDOWS_NAMESPACE_REJECTED")
    return value


if os.name == "nt":
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    FILE_READ_DATA = 0x0001
    FILE_LIST_DIRECTORY = 0x0001
    READ_CONTROL = 0x00020000
    FILE_SHARE_ALL = 0x00000001 | 0x00000002 | 0x00000004
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    FILE_ID_INFO_CLASS = 18
    FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
    OWNER_SECURITY_INFORMATION = 0x00000001
    DACL_SECURITY_INFORMATION = 0x00000004
    SE_FILE_OBJECT = 1
    TOKEN_QUERY = 0x0008
    TOKEN_USER_CLASS = 1

    class _FileId128(ctypes.Structure):
        _fields_ = [("identifier", ctypes.c_ubyte * 16)]

    class _FileIdInfo(ctypes.Structure):
        _fields_ = [
            ("volume_serial_number", ctypes.c_ulonglong),
            ("file_id", _FileId128),
        ]

    class _FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("file_attributes", wintypes.DWORD),
            ("reparse_tag", wintypes.DWORD),
        ]

    class _Trustee(ctypes.Structure):
        _fields_ = [
            ("multiple_trustee", ctypes.c_void_p),
            ("multiple_trustee_operation", wintypes.DWORD),
            ("trustee_form", wintypes.DWORD),
            ("trustee_type", wintypes.DWORD),
            ("name", ctypes.c_void_p),
        ]

    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.GetFileSizeEx.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_longlong),
    ]
    _kernel32.GetFileSizeEx.restype = wintypes.BOOL
    _kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    _kernel32.ReadFile.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    _kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _advapi32.GetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.GetSecurityInfo.restype = wintypes.DWORD
    _advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    _advapi32.OpenProcessToken.restype = wintypes.BOOL
    _advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _advapi32.GetTokenInformation.restype = wintypes.BOOL
    _advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _advapi32.EqualSid.restype = wintypes.BOOL
    _advapi32.CreateWellKnownSid.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _advapi32.CreateWellKnownSid.restype = wintypes.BOOL
    _advapi32.GetEffectiveRightsFromAclW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_Trustee),
        ctypes.POINTER(wintypes.DWORD),
    ]
    _advapi32.GetEffectiveRightsFromAclW.restype = wintypes.DWORD


@dataclass(frozen=True)
class WindowsFileIdentity:
    volume_serial: int
    file_id: bytes
    sha256: str


class _OwnedHandle:
    def __init__(self, value):
        self.value = value

    def close(self) -> None:
        if os.name == "nt" and self.value not in {None, INVALID_HANDLE_VALUE}:
            _kernel32.CloseHandle(self.value)
            self.value = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsTrustedStateError("TRUST_STATE_PLATFORM_UNSUPPORTED")


def _open_handle(path: Path, *, directory: bool) -> _OwnedHandle:
    _require_windows()
    flags = FILE_FLAG_OPEN_REPARSE_POINT
    if directory:
        flags |= FILE_FLAG_BACKUP_SEMANTICS
    handle = _kernel32.CreateFileW(
        str(path),
        READ_CONTROL | (FILE_LIST_DIRECTORY if directory else FILE_READ_DATA),
        FILE_SHARE_ALL,
        None,
        OPEN_EXISTING,
        flags,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        raise WindowsTrustedStateError("WINDOWS_HANDLE_OPEN_FAILED")
    return _OwnedHandle(handle)


def _reject_reparse(handle: _OwnedHandle) -> None:
    info = _FileAttributeTagInfo()
    if not _kernel32.GetFileInformationByHandleEx(
        handle.value,
        FILE_ATTRIBUTE_TAG_INFO_CLASS,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        raise WindowsTrustedStateError("WINDOWS_HANDLE_INFO_FAILED")
    if info.file_attributes & FILE_ATTRIBUTE_REPARSE_POINT or info.reparse_tag:
        raise WindowsTrustedStateError("REPARSE_POINT_REJECTED")


def _file_id(handle: _OwnedHandle) -> tuple[int, bytes]:
    info = _FileIdInfo()
    if not _kernel32.GetFileInformationByHandleEx(
        handle.value,
        FILE_ID_INFO_CLASS,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        raise WindowsTrustedStateError("WINDOWS_HANDLE_INFO_FAILED")
    identifier = bytes(info.file_id.identifier)
    if not info.volume_serial_number or not any(identifier):
        raise WindowsTrustedStateError("WINDOWS_FILE_ID_CHANGED")
    return int(info.volume_serial_number), identifier


def _read_bounded(handle: _OwnedHandle, max_bytes: int) -> bytes:
    size = ctypes.c_longlong()
    if not _kernel32.GetFileSizeEx(handle.value, ctypes.byref(size)):
        raise WindowsTrustedStateError("WINDOWS_HANDLE_INFO_FAILED")
    if size.value < 0 or size.value > max_bytes:
        raise WindowsTrustedStateError("TRUST_STATE_TOO_LARGE")
    if size.value == 0:
        return b""
    buffer = ctypes.create_string_buffer(size.value)
    read = wintypes.DWORD()
    if not _kernel32.ReadFile(
        handle.value,
        buffer,
        size.value,
        ctypes.byref(read),
        None,
    ) or read.value != size.value:
        raise WindowsTrustedStateError("TRUST_STATE_READ_FAILED")
    return buffer.raw[: read.value]


def _current_user_sid() -> tuple[_OwnedHandle, ctypes.Array, ctypes.c_void_p]:
    token = wintypes.HANDLE()
    if not _advapi32.OpenProcessToken(
        _kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)
    ):
        raise WindowsTrustedStateError("WINDOWS_OWNER_MISMATCH")
    owned = _OwnedHandle(token)
    size = wintypes.DWORD()
    _advapi32.GetTokenInformation(
        token, TOKEN_USER_CLASS, None, 0, ctypes.byref(size)
    )
    if not size.value:
        owned.close()
        raise WindowsTrustedStateError("WINDOWS_OWNER_MISMATCH")
    buffer = ctypes.create_string_buffer(size.value)
    if not _advapi32.GetTokenInformation(
        token,
        TOKEN_USER_CLASS,
        buffer,
        size,
        ctypes.byref(size),
    ):
        owned.close()
        raise WindowsTrustedStateError("WINDOWS_OWNER_MISMATCH")
    sid = ctypes.c_void_p.from_buffer(buffer).value
    return owned, buffer, ctypes.c_void_p(sid)


def _well_known_sid(kind: int) -> tuple[ctypes.Array, ctypes.c_void_p]:
    size = wintypes.DWORD(68)
    buffer = ctypes.create_string_buffer(size.value)
    if not _advapi32.CreateWellKnownSid(
        kind, None, buffer, ctypes.byref(size)
    ):
        raise WindowsTrustedStateError("WINDOWS_DACL_UNTRUSTED")
    return buffer, ctypes.cast(buffer, ctypes.c_void_p)


def _validate_security(handle: _OwnedHandle) -> None:
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    status = _advapi32.GetSecurityInfo(
        handle.value,
        SE_FILE_OBJECT,
        OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if status != 0 or not owner.value or not dacl.value:
        raise WindowsTrustedStateError("WINDOWS_DACL_UNTRUSTED")
    try:
        token, token_buffer, user_sid = _current_user_sid()
        with token:
            if not _advapi32.EqualSid(owner, user_sid):
                raise WindowsTrustedStateError("WINDOWS_OWNER_MISMATCH")
            # Keep token_buffer alive through EqualSid.
            _ = token_buffer
        # WinWorldSid, WinAuthenticatedUserSid, WinBuiltinUsersSid.
        for sid_kind in (1, 17, 27):
            sid_buffer, sid = _well_known_sid(sid_kind)
            trustee = _Trustee(None, 0, 0, 0, sid)
            rights = wintypes.DWORD()
            if _advapi32.GetEffectiveRightsFromAclW(
                dacl, ctypes.byref(trustee), ctypes.byref(rights)
            ) != 0:
                raise WindowsTrustedStateError("WINDOWS_DACL_UNTRUSTED")
            _ = sid_buffer
            if rights.value & _BROAD_WRITE_MASK:
                raise WindowsTrustedStateError("WINDOWS_DACL_UNTRUSTED")
    finally:
        if descriptor.value:
            _kernel32.LocalFree(descriptor)


class WindowsTrustedStateAdapter:
    """Handle-based verifier for native-owned Windows trust state.

    Mutation remains in the Rust/DPAPI authority.  The sidecar receives only
    the verified bytes and opaque identity from this adapter.
    """

    def __init__(self, scope: Path) -> None:
        _require_windows()
        self.scope = Path(scope)
        text = str(self.scope)
        if (
            not self.scope.is_absolute()
            or text.startswith(("\\\\", "\\?\\", "\\.\\"))
            or not re.match(r"^[A-Za-z]:\\", text)
        ):
            raise WindowsTrustedStateError("WINDOWS_NAMESPACE_REJECTED")

    def _walk(self, relative_name: str) -> tuple[Path, _OwnedHandle]:
        name = validate_relative_name(relative_name)
        current = Path(self.scope.anchor)
        for part in self.scope.parts[1:]:
            current /= part
            handle = _open_handle(current, directory=True)
            try:
                _reject_reparse(handle)
            except Exception:
                handle.close()
                raise
            handle.close()
        target = self.scope / name
        handle = _open_handle(target, directory=False)
        _reject_reparse(handle)
        _validate_security(handle)
        return target, handle

    def read_verified(
        self,
        relative_name: str,
        *,
        max_bytes: int,
    ) -> tuple[bytes, WindowsFileIdentity]:
        _target, handle = self._walk(relative_name)
        try:
            before = _file_id(handle)
            payload = _read_bounded(handle, max_bytes)
            after = _file_id(handle)
            if before != after:
                raise WindowsTrustedStateError("WINDOWS_FILE_ID_CHANGED")
            return payload, WindowsFileIdentity(
                volume_serial=before[0],
                file_id=before[1],
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        finally:
            handle.close()

    def assert_unchanged(
        self,
        relative_name: str,
        expected: WindowsFileIdentity,
    ) -> None:
        payload, actual = self.read_verified(relative_name, max_bytes=64 * 1024)
        _ = payload
        if actual != expected:
            raise WindowsTrustedStateError("WINDOWS_FILE_ID_CHANGED")
