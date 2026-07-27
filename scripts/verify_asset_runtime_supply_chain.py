#!/usr/bin/env python3
from __future__ import annotations


DEFERRED_CODE = "INSTALLED_ARTIFACT_SUPPLY_CHAIN_E2E_DEFERRED"


def main() -> int:
    # AP60-006 is explicitly deferred until a real installed distribution
    # exists. Static lock/SBOM text is not accepted as installed-artifact proof.
    print("ASSET_RUNTIME_SUPPLY_CHAIN_OK=0")
    print(f"ERROR_CODE={DEFERRED_CODE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
