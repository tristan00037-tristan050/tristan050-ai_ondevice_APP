from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from butler_pc_core.learning_capability.contracts import AuthorityProbe
from butler_pc_core.learning_capability.generation_store import (
    DurableGenerationStore,
    GenerationStoreError,
)
from butler_pc_core.learning_capability.service import LearningCapabilityService


pytestmark = pytest.mark.no_sidecar_token


@dataclass
class _StableAuthority:
    key: str
    revision_value: str

    def revision(self) -> str:
        return self.revision_value

    def probe(self) -> AuthorityProbe:
        return AuthorityProbe(
            key=self.key,
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


class _ProbeMismatchAuthority(_StableAuthority):
    def probe(self) -> AuthorityProbe:
        return AuthorityProbe(
            key=self.key,
            available=True,
            registered=True,
            consumer_bound=True,
            preview_only=False,
            revision="f" * 64,
            evidence_digest="2" * 64,
        )


class _RetryThenStableAuthority(_StableAuthority):
    def __init__(self, key: str) -> None:
        super().__init__(key=key, revision_value="6" * 64)
        self.calls = 0

    def revision(self) -> str:
        self.calls += 1
        return "7" * 64 if self.calls == 1 else self.revision_value


class _WrongProbeKeyAuthority(_StableAuthority):
    def probe(self) -> AuthorityProbe:
        probe = super().probe()
        return AuthorityProbe(
            key="company_facts",
            available=probe.available,
            registered=probe.registered,
            consumer_bound=probe.consumer_bound,
            preview_only=probe.preview_only,
            revision=probe.revision,
            evidence_digest=probe.evidence_digest,
        )


class _InvalidDigestAuthority(_StableAuthority):
    def probe(self) -> AuthorityProbe:
        probe = super().probe()
        return AuthorityProbe(
            key=probe.key,
            available=probe.available,
            registered=probe.registered,
            consumer_bound=probe.consumer_bound,
            preview_only=probe.preview_only,
            revision=probe.revision,
            evidence_digest="not-a-digest",
        )


def _authorities(first) -> tuple:
    return (
        first,
        _StableAuthority("company_facts", "3" * 64),
        _StableAuthority("company_formats", "4" * 64),
        _StableAuthority("folder_learning", "5" * 64),
    )


def test_two_unstable_snapshot_attempts_fail_closed(tmp_path):
    racing = _RacingAuthority("company_rules")
    service = LearningCapabilityService(
        authorities=_authorities(racing),
        generation_store=DurableGenerationStore(tmp_path / "generation.json"),
    )
    with pytest.raises(Exception) as captured:
        service.snapshot()
    assert (
        getattr(captured.value, "reason", None)
        == "AUTHORITY_CHANGED_DURING_SNAPSHOT"
    )
    assert racing.calls == 4
    assert not (tmp_path / "generation.json").exists()


def test_probe_revision_must_equal_both_outer_revisions(tmp_path):
    service = LearningCapabilityService(
        authorities=_authorities(
            _ProbeMismatchAuthority("company_rules", "1" * 64)
        ),
        generation_store=DurableGenerationStore(tmp_path / "generation.json"),
    )
    with pytest.raises(Exception) as captured:
        service.snapshot()
    assert (
        getattr(captured.value, "reason", None)
        == "AUTHORITY_CHANGED_DURING_SNAPSHOT"
    )
    assert not (tmp_path / "generation.json").exists()


def test_one_changed_authority_blocks_the_entire_snapshot(tmp_path):
    racing = _RacingAuthority("company_rules")
    service = LearningCapabilityService(
        authorities=_authorities(racing),
        generation_store=DurableGenerationStore(tmp_path / "generation.json"),
    )
    with pytest.raises(Exception) as captured:
        service.snapshot()
    assert (
        getattr(captured.value, "reason", None)
        == "AUTHORITY_CHANGED_DURING_SNAPSHOT"
    )


def test_first_unstable_attempt_is_discarded_and_second_stable_attempt_succeeds(
    tmp_path,
):
    authority = _RetryThenStableAuthority("company_rules")
    service = LearningCapabilityService(
        authorities=_authorities(authority),
        generation_store=DurableGenerationStore(tmp_path / "generation.json"),
    )
    assert service.snapshot().generation == 1
    assert authority.calls == 4


def test_duplicate_authority_key_fails_before_generation(tmp_path):
    stable = _StableAuthority("company_rules", "1" * 64)
    with pytest.raises(ValueError, match="AUTHORITY_KEYSET_INVALID"):
        LearningCapabilityService(
            authorities=(
                stable,
                _StableAuthority("company_rules", "2" * 64),
                _StableAuthority("company_formats", "3" * 64),
                _StableAuthority("folder_learning", "4" * 64),
            ),
            generation_store=DurableGenerationStore(
                tmp_path / "duplicate.json"
            ),
        )


def test_missing_or_extra_authority_key_fails_before_generation(tmp_path):
    stable = _StableAuthority("company_rules", "1" * 64)
    with pytest.raises(ValueError, match="AUTHORITY_KEYSET_INVALID"):
        LearningCapabilityService(
            authorities=_authorities(stable)[:-1],
            generation_store=DurableGenerationStore(tmp_path / "missing.json"),
        )
    with pytest.raises(ValueError, match="AUTHORITY_KEYSET_INVALID"):
        LearningCapabilityService(
            authorities=(
                *_authorities(stable),
                _StableAuthority("extra", "6" * 64),
            ),
            generation_store=DurableGenerationStore(tmp_path / "extra.json"),
        )


def test_probe_key_mismatch_fails_before_generation(tmp_path):
    service = LearningCapabilityService(
        authorities=_authorities(_WrongProbeKeyAuthority("company_rules", "1" * 64)),
        generation_store=DurableGenerationStore(tmp_path / "wrong-key.json"),
    )
    with pytest.raises(Exception) as captured:
        service.snapshot()
    assert getattr(captured.value, "reason", None) == "CONTRACT_MISMATCH"
    assert not (tmp_path / "wrong-key.json").exists()


def test_invalid_probe_revision_or_evidence_digest_is_rejected(tmp_path):
    invalid_authorities = (
        _StableAuthority("company_rules", "not-a-digest"),
        _InvalidDigestAuthority("company_rules", "1" * 64),
    )
    for index, authority in enumerate(invalid_authorities):
        path = tmp_path / f"generation-{index}.json"
        service = LearningCapabilityService(
            authorities=_authorities(authority),
            generation_store=DurableGenerationStore(path),
        )
        with pytest.raises(Exception) as captured:
            service.snapshot()
        assert getattr(captured.value, "reason", None) == "CONTRACT_MISMATCH"
        assert not path.exists()


def test_failed_snapshot_attempt_does_not_advance_generation(tmp_path):
    path = tmp_path / "generation.json"
    service = LearningCapabilityService(
        authorities=_authorities(_RacingAuthority("company_rules")),
        generation_store=DurableGenerationStore(path),
    )
    with pytest.raises(Exception):
        service.snapshot()
    assert not path.exists()


def test_same_snapshot_digest_does_not_advance_generation(tmp_path):
    path = tmp_path / "generation.json"
    first_store = DurableGenerationStore(path)
    first = first_store.generation_for("a" * 64)
    assert first_store.generation_for("a" * 64) == first
    assert DurableGenerationStore(path).generation_for("a" * 64) == first


def test_changed_snapshot_digest_advances_generation_once_under_lock(tmp_path):
    path = tmp_path / "generation.json"
    first = DurableGenerationStore(path).generation_for("a" * 64)
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


def test_concurrent_changed_snapshots_receive_distinct_generations(tmp_path):
    path = tmp_path / "generation.json"

    def issue(digest: str) -> int:
        return DurableGenerationStore(path).generation_for(digest)

    with ThreadPoolExecutor(max_workers=2) as executor:
        generations = set(
            executor.map(issue, ("a" * 64, "b" * 64))
        )
    assert generations == {1, 2}
