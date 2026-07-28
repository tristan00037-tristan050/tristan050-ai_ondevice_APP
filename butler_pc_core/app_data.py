from __future__ import annotations

import os
from pathlib import Path


class AppDataPathError(RuntimeError):
    pass


def product_data_root(component: str, *, legacy_name: str) -> Path:
    """Return a device-local persistent root without accepting relative app data."""

    configured = os.environ.get("BUTLER_APP_DATA_DIR", "").strip()
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            raise AppDataPathError("APP_DATA_DIR_NOT_ABSOLUTE")
        return root / component
    # The native launcher always supplies BUTLER_APP_DATA_DIR. Preserve the
    # documented repository/dev launcher behavior when it is intentionally
    # absent instead of silently writing into a user's home directory.
    return Path(legacy_name)
