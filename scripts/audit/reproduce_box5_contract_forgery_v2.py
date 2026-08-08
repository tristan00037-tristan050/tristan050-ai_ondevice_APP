#!/usr/bin/env python3
"""Adapt the preserved v1 contract attacks to the current product route.

The original audit program remains evidence of the vulnerable reference
contract.  This adapter executes the current composition/HTTP regressions: the
product installer has no caller-supplied verifier/session dependency, forged
role/capability fields are rejected, and the accounting database receives no
side effect.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST = (
    "tests/accounting/assignment/test_authorization_product_route.py::"
    "test_contract_forgery_inputs_are_not_product_route_dependencies"
)
COMPOSITION_TEST = (
    "tests/accounting/assignment/test_authorization_product_route.py::"
    "test_product_composition_has_one_shared_transport_authenticator"
)


def main() -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--disable-warnings",
            TEST,
            COMPOSITION_TEST,
        ],
        cwd=ROOT,
        check=False,
    )
    passed = completed.returncode == 0
    print("ATTACK_ID=BOX5-CORRECTION-V2-PROOF-CALLBACK-01")
    print(f"PRODUCT_ROUTE_CALLBACK_INPUT_ACCEPTED={str(not passed).lower()}")
    print("ATTACK_ID=BOX5-CORRECTION-V2-DIRECT-SESSION-02")
    print(f"PRODUCT_ROUTE_SYNTHETIC_SESSION_ACCEPTED={str(not passed).lower()}")
    print("DATABASE_SIDE_EFFECTS=0" if passed else "DATABASE_SIDE_EFFECTS=UNKNOWN")
    print("VERDICT=PASS_FORGERIES_BLOCKED" if passed else "VERDICT=FAIL_REGRESSION")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
