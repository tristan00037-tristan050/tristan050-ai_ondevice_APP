from __future__ import annotations

import pytest

from scripts.verify_asset_runtime_supply_chain import DEFERRED_CODE, main

pytestmark = pytest.mark.no_sidecar_token


def test_installed_distribution_matches_lock_and_vendor_commit(
    capsys,
) -> None:
    assert main() == 0
    output = capsys.readouterr().out.splitlines()
    assert output == [
        "ASSET_RUNTIME_SUPPLY_CHAIN_OK=0",
        f"ERROR_CODE={DEFERRED_CODE}",
    ]
