from __future__ import annotations

import math
import random
from collections.abc import Sequence

from .errors import ExitCode, FailClass, GateError


def summarize_integer_points(points: Sequence[int]) -> dict[str, object]:
    if not points or any(not isinstance(value, int) or isinstance(value, bool) for value in points):
        raise GateError(FailClass.SCHEMA_INVALID, "STAT_POINTS", exit_code=ExitCode.SCHEMA)
    ordered = sorted(points)
    count = len(ordered)
    if count % 2:
        median_num, median_den = ordered[count // 2], 1
    else:
        median_num, median_den = ordered[count // 2 - 1] + ordered[count // 2], 2
    p95 = ordered[max(0, math.ceil(0.95 * count) - 1)]
    return {
        "count": count,
        "raw_points": list(points),
        "median_numerator": median_num,
        "median_denominator": median_den,
        "p95_nearest_rank": p95,
        "mean_numerator": sum(points),
        "mean_denominator": count,
    }


def paired_bootstrap_mean_ci(
    candidate_a: Sequence[int],
    candidate_b: Sequence[int],
    *,
    seed: int,
    iterations: int,
) -> dict[str, int]:
    if len(candidate_a) != len(candidate_b) or not candidate_a or iterations < 1000:
        raise GateError(FailClass.SCHEMA_INVALID, "PAIRED_BOOTSTRAP_INPUT", exit_code=ExitCode.SCHEMA)
    differences = [a - b for a, b in zip(candidate_a, candidate_b, strict=True)]
    rng = random.Random(seed)
    sample_count = len(differences)
    estimates: list[int] = []
    for _ in range(iterations):
        total = sum(differences[rng.randrange(sample_count)] for _ in range(sample_count))
        estimates.append(_round_half_away(total, sample_count))
    estimates.sort()
    lower = estimates[max(0, math.ceil(0.025 * iterations) - 1)]
    upper = estimates[max(0, math.ceil(0.975 * iterations) - 1)]
    return {
        "paired_count": sample_count,
        "bootstrap_iterations": iterations,
        "seed": seed,
        "mean_difference_scaled": _round_half_away(sum(differences), sample_count),
        "ci95_lower_scaled": lower,
        "ci95_upper_scaled": upper,
    }


def _round_half_away(numerator: int, denominator: int) -> int:
    sign = -1 if numerator < 0 else 1
    q, r = divmod(abs(numerator), denominator)
    return sign * (q + (1 if 2 * r >= denominator else 0))

