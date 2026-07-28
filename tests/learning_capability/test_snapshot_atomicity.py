from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from butler_pc_core.learning_capability.contracts import AuthorityProbe
from butler_pc_core.learning_capability.generation_store import (
    DurableGenerationStore,
    GenerationStoreError,
)
from butler_pc_core.learning_capability.service import LearningCapabilityService


@dataclass
class _StableAuthority:
    key: str
    revision_value: str

    def revision(self) -> str:
        return self.revision_value

    def probe(self) -> AuthorityProbe:
        return AuthorityProbe(
            available=True,
            registered=True,
            consumer_bound=True,
            preview_only=False,
            revision=self.revision_value,
            evidence_digest="2" * 64,
        )


class _RacingAuthority(_StableAuthority):
    def __init__(self, key: str) -> None:
        super().__init__(key=key, revision_value="1" * 64)
        self.calls = 0

    def revision(self) -> str:
        self.calls += 1
        return f"{self.calls:064x}"


def _authorities(first) -> tuple:
    return (
        first,
        _StableAuthority("company_facts", "3" * 64),
        _StableAuthority("company_formats", "4" * 64),
        _StableAuthority("folder_learning", "5" * 64),
    )


def test_revision_race_retries_once_then_fails_closed(tmp_path):
    racing = _RacingAuthority("company_rules")
    service = LearningCapabilityService(
        authorities=_authorities(racing),
        generation_store=DurableGenerationStore(tmp_path / "generation.json"),
    )
    with pytest.raises(Exception) as captured:
        service.snapshot()
    assert getattr(captured.value, "reason", None) == "AUTHORITY_CHANGED"
    assert racing.calls == 4
    assert not (tmp_path / "generation.json").exists()


def test_generation_is_stable_for_same_digest_and_monotonic_across_restart(
    tmp_path,
):
    path = tmp_path / "generation.json"
    first_store = DurableGenerationStore(path)
    first = first_store.generation_for("a" * 64)
    assert first_store.generation_for("a" * 64) == first

    restarted = DurableGenerationStore(path)
    second = restarted.generation_for("b" * 64)
    assert second > first
    assert DurableGenerationStore(path).generation_for("b" * 64) == second


def test_generation_store_corruption_lock_failure_and_overflow_fail_closed(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "generation.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(GenerationStoreError):
        DurableGenerationStore(path).generation_for("a" * 64)

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "last_generation": 9_007_199_254_740_991,
                "last_snapshot_digest": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GenerationStoreError):
        DurableGenerationStore(path).generation_for("b" * 64)

    store = DurableGenerationStore(tmp_path / "locked.json")

    @contextmanager
    def failed_lock():
        raise GenerationStoreError("GENERATION_LOCK_FAILED")
        yield

    monkeypatch.setattr(store, "_locked", failed_lock)
    with pytest.raises(GenerationStoreError):
        store.generation_for("c" * 64)
    assert not store.path.exists()

