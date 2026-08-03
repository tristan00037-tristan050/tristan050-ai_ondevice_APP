from __future__ import annotations

import random

from butler_pc_core.helper1.canonical_json import (
    canonicalize_butler_cj1,
    require_canonical_butler_cj1,
)


def test_deterministic_canonical_vectors_for_seeds_1_through_100() -> None:
    first_pass: list[bytes] = []
    second_pass: list[bytes] = []
    for destination in (first_pass, second_pass):
        for seed in range(1, 101):
            rng = random.Random(seed)
            value = {
                "seed": seed,
                "nonce": rng.randbytes(16).hex(),
                "counts": [rng.randrange(0, 1_000_000) for _ in range(8)],
                "accepted": bool(rng.randrange(0, 2)),
            }
            encoded = canonicalize_butler_cj1(value)
            assert require_canonical_butler_cj1(encoded) == value
            destination.append(encoded)
    assert first_pass == second_pass
