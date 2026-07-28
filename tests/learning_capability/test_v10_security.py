from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from butler_pc_core.learning_capability.contracts import AuthorityProbe
from butler_pc_core.learning_capability.generation_store import (
    DurableGenerationStore,
    GenerationStoreError,
)
from butler_pc_core.learning_capability.service import LearningCapabilityService
from butler_pc_core.strict_json import (
    StrictJsonError,
    dump_canonical_bytes,
    load_strict_bytes,
)


@dataclass
class _Authority:
    key: str
    revision_value: str
    probe_revision: str | None = None
    probe_key: str | None = None

    def revision(self) -> str:
        return self.revision_value

    def probe(self) -> AuthorityProbe:
        return AuthorityProbe(
            key=self.probe_key or self.key,
            available=True,
            registered=True,
            consumer_bound=True,
            preview_only=False,
            revision=self.probe_revision or self.revision_value,
            evidence_digest="e" * 64,
        )


def _authorities(first: _Authority | None = None) -> tuple[_Authority, ...]:
    return (
        first or _Authority("company_rules", "1" * 64),
        _Authority("company_facts", "2" * 64),
        _Authority("company_formats", "3" * 64),
        _Authority("folder_learning", "4" * 64),
    )


def test_before_after_equal_but_probe_revision_mismatch_fails_closed(tmp_path):
    service = LearningCapabilityService(
        _authorities(
            _Authority(
                "company_rules",
                "1" * 64,
                probe_revision="9" * 64,
            )
        ),
        DurableGenerationStore(tmp_path / "generation.json"),
    )
    with pytest.raises(Exception) as captured:
        service.snapshot()
    assert captured.value.reason == "AUTHORITY_CHANGED_DURING_SNAPSHOT"
    assert not (tmp_path / "generation.json").exists()


def test_duplicate_missing_extra_authorities_are_rejected_before_mapping(tmp_path):
    store = DurableGenerationStore(tmp_path / "generation.json")
    for authorities in (
        _authorities()[:-1],
        (*_authorities(), _Authority("company_rules", "5" * 64)),
        (
            _Authority("company_rules", "1" * 64),
            _Authority("company_facts", "2" * 64),
            _Authority("folder_learning", "4" * 64),
            _Authority("company_formats", "3" * 64),
        ),
    ):
        with pytest.raises(ValueError):
            LearningCapabilityService(authorities, store)


def test_probe_key_mismatch_is_rejected(tmp_path):
    service = LearningCapabilityService(
        _authorities(
            _Authority(
                "company_rules",
                "1" * 64,
                probe_key="company_facts",
            )
        ),
        DurableGenerationStore(tmp_path / "generation.json"),
    )
    with pytest.raises(Exception) as captured:
        service.snapshot()
    assert captured.value.reason == "AUTHORITY_CHANGED_DURING_SNAPSHOT"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b'{"a":1,"a":2}', "JSON_DUPLICATE_KEY"),
        (b'{"a":{"b":1,"b":2}}', "JSON_DUPLICATE_KEY"),
        (b'{"a":NaN}', "JSON_NON_FINITE_FORBIDDEN"),
        (b'{"a":Infinity}', "JSON_NON_FINITE_FORBIDDEN"),
        (b"\xff", "JSON_UTF8_INVALID"),
        (b'\xef\xbb\xbf{"a":1}', "JSON_BOM_FORBIDDEN"),
        (b"[]", "JSON_ROOT_NOT_OBJECT"),
        (b"null", "JSON_ROOT_NOT_OBJECT"),
    ],
)
def test_strict_json_rejects_ambiguous_or_noncanonical_input(payload, code):
    with pytest.raises(StrictJsonError) as captured:
        load_strict_bytes(payload)
    assert str(captured.value) == code


def test_strict_json_enforces_size_depth_nodes_strings_and_integer_bounds():
    payloads = (
        b'{"a":"' + b"x" * 8193 + b'"}',
        b'{"a":' * 17 + b"1" + b"}" * 17,
        b'{"a":12345678901234567}',
        b'{"a":' + b"[" * 16 + b"0" + b"]" * 16 + b"}",
        b"{" + b'"a":1,' * 2048 + b'"z":1}',
        b'{"a":"' + b"x" * (64 * 1024) + b'"}',
    )
    for payload in payloads:
        with pytest.raises(StrictJsonError):
            load_strict_bytes(payload)


def test_strict_json_round_trip_is_canonical():
    value = load_strict_bytes(b'{"z":2,"a":{"ok":true}}')
    assert dump_canonical_bytes(value) == b'{"a":{"ok":true},"z":2}'


def test_generation_store_rejects_symlink_and_wide_permissions(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "generation.json"
    link.symlink_to(target)
    with pytest.raises(GenerationStoreError):
        DurableGenerationStore(link).generation_for("a" * 64)
    link.unlink()
    link.write_text("{}", encoding="utf-8")
    link.chmod(0o644)
    with pytest.raises(GenerationStoreError):
        DurableGenerationStore(link).generation_for("a" * 64)


def test_generation_store_requires_absolute_root():
    with pytest.raises(GenerationStoreError):
        DurableGenerationStore(Path("relative/generation.json"))


def test_generation_store_rejects_intermediate_directory_symlink(tmp_path):
    trusted = tmp_path / "trusted"
    trusted.mkdir(mode=0o700)
    link = tmp_path / "linked"
    link.symlink_to(trusted, target_is_directory=True)
    with pytest.raises(GenerationStoreError):
        DurableGenerationStore(link / "generation.json").generation_for(
            "a" * 64
        )


def test_concurrent_generation_changes_are_unique_and_monotonic(tmp_path):
    path = tmp_path / "generation.json"

    def write(digest: str) -> int:
        return DurableGenerationStore(path).generation_for(digest)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ("a" * 64, "b" * 64)))
    assert len(set(results)) == 2
    assert max(results) - min(results) == 1
    os.chmod(path, 0o600)
