from __future__ import annotations

import ctypes
import os
import platform
from pathlib import Path

from .errors import block

AT_FDCWD = -2
RENAME_NOREPLACE = 1
RENAME_EXCL = 0x00000004


def _encoded(path: Path) -> bytes:
    return os.fsencode(path)


def atomic_publish_noreplace(source: Path, target: Path) -> None:
    """Atomically publish a staged tree and refuse every existing target."""
    system = platform.system()
    libc = ctypes.CDLL(None, use_errno=True)
    if system == "Linux":
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise block("PUBLISH_ATOMIC_UNAVAILABLE")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            AT_FDCWD,
            _encoded(source),
            AT_FDCWD,
            _encoded(target),
            RENAME_NOREPLACE,
        )
    elif system == "Darwin":
        renamex_np = getattr(libc, "renamex_np", None)
        if renamex_np is None:
            raise block("PUBLISH_ATOMIC_UNAVAILABLE")
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(_encoded(source), _encoded(target), RENAME_EXCL)
    else:
        raise block("BLOCK_PLATFORM_UNSUPPORTED")
    if result != 0:
        error = ctypes.get_errno()
        if error in {17, 39}:  # EEXIST, ENOTEMPTY
            raise block("PUBLISH_TARGET_EXISTS")
        raise block("PUBLISH_ATOMIC_FAILED")
