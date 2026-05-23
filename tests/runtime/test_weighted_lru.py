from __future__ import annotations

from datetime import datetime, timedelta

from butler_pc_core.runtime.weighted_lru import ModelEntry, WeightedLRU

NOW = datetime(2026, 5, 22, 14, 0, 0)


def entry(model_id: str, minutes_old: int, size: float = 100, reload_ms: float = 100, active: int = 0, pinned_minutes: int | None = None, mem: int = 0, thermal: int = 0) -> ModelEntry:
    pinned_until = NOW + timedelta(minutes=pinned_minutes) if pinned_minutes is not None else None
    return ModelEntry(
        model_id=model_id,
        model_size_mb=size,
        reload_cost_ms=reload_ms,
        last_used_at=NOW - timedelta(minutes=minutes_old),
        active_session_count=active,
        pinned_until=pinned_until,
        memory_pressure_level=mem,
        thermal_pressure_level=thermal,
    )


def test_recency_eviction():
    policy = WeightedLRU([entry("new", 1), entry("old", 60)])
    assert policy.choose_evict_candidate(NOW).model_id == "old"


def test_size_priority():
    policy = WeightedLRU([entry("small", 10, size=10), entry("large", 10, size=1000)])
    assert policy.choose_evict_candidate(NOW).model_id == "large"


def test_active_session_protection():
    policy = WeightedLRU([entry("active", 100, active=1)])
    assert policy.choose_evict_candidate(NOW) is None
    assert policy.choose_evict_candidate(NOW, force=True).model_id == "active"


def test_pinned_protection():
    policy = WeightedLRU([entry("pinned", 100, pinned_minutes=10)])
    assert policy.choose_evict_candidate(NOW) is None
    assert policy.choose_evict_candidate(NOW, force=True).model_id == "pinned"


def test_pressure_acceleration():
    base = entry("base", 10, size=200)
    pressured = entry("pressured", 10, size=200, mem=8, thermal=8)
    policy = WeightedLRU([base, pressured])
    assert policy.evict_score(pressured, NOW) > policy.evict_score(base, NOW)


def test_reload_cost_protection():
    cheap = entry("cheap", 10, size=200, reload_ms=10)
    expensive = entry("expensive", 10, size=200, reload_ms=100000)
    policy = WeightedLRU([cheap, expensive])
    assert policy.evict_score(cheap, NOW) > policy.evict_score(expensive, NOW)


def test_full_eviction_scenario():
    first = entry("b_model", 10, size=500)
    second = entry("a_model", 10, size=500)
    active = entry("active", 1000, size=5000, active=1)
    pinned = entry("pinned", 1000, size=5000, pinned_minutes=60)
    policy = WeightedLRU([first, second, active, pinned])
    assert policy.choose_evict_candidate(NOW).model_id == "a_model"
