from __future__ import annotations

import pytest

from butler_pc_core.home import store


@pytest.fixture(autouse=True)
def use_file_credentials_for_isolated_store_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests out of the user's macOS Keychain.

    Production continues to use Keychain on Darwin. The test-only platform
    override exercises the same encrypted store with an isolated 0600 key file.
    """

    monkeypatch.setattr(store.sys, "platform", "linux")
