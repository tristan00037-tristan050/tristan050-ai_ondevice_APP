from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .authorities import AuthorityReadError, LearningAuthority
from .contracts import (
    CAPABILITY_KEYS,
    CapabilityState,
    LearningCapabilityError,
    LearningCapabilitySnapshot,
    derive_state,
    lower_hex_digest,
)
from .generation_store import DurableGenerationStore, GenerationStoreError


@dataclass
class LearningCapabilityService:
    authorities: Sequence[LearningAuthority]
    generation_store: DurableGenerationStore

    def __post_init__(self) -> None:
        keys = tuple(authority.key for authority in self.authorities)
        if (
            len(keys) != len(CAPABILITY_KEYS)
            or len(set(keys)) != len(keys)
            or set(keys) != set(CAPABILITY_KEYS)
        ):
            raise ValueError("AUTHORITY_KEYSET_INVALID")
        if keys != CAPABILITY_KEYS:
            raise ValueError("AUTHORITY_ORDER_INVALID")

    def snapshot(self) -> LearningCapabilitySnapshot:
        try:
            for _attempt in range(2):
                before = {
                    authority.key: authority.revision()
                    for authority in self.authorities
                }
                probes = {
                    authority.key: authority.probe()
                    for authority in self.authorities
                }
                after = {
                    authority.key: authority.revision()
                    for authority in self.authorities
                }
                if (
                    tuple(before) != CAPABILITY_KEYS
                    or tuple(probes) != CAPABILITY_KEYS
                    or tuple(after) != CAPABILITY_KEYS
                ):
                    raise LearningCapabilityError("CONTRACT_MISMATCH")
                if any(
                    probes[key].key != key
                    for key in CAPABILITY_KEYS
                ):
                    raise LearningCapabilityError("CONTRACT_MISMATCH")
                if not all(
                    before[key] == probes[key].revision == after[key]
                    for key in CAPABILITY_KEYS
                ):
                    continue

                states = {
                    key: derive_state(probes[key])
                    for key in CAPABILITY_KEYS
                }
                if any(
                    state is CapabilityState.UNKNOWN
                    for state in states.values()
                ):
                    raise LearningCapabilityError("AUTHORITY_INCOMPLETE")
                snapshot_digest = lower_hex_digest(
                    {
                        "schema_version": 1,
                        "revisions": {
                            key: probes[key].revision
                            for key in CAPABILITY_KEYS
                        },
                        "states": {
                            key: states[key].value for key in CAPABILITY_KEYS
                        },
                        "evidence_digests": {
                            key: probes[key].evidence_digest
                            for key in CAPABILITY_KEYS
                        },
                    }
                )
                try:
                    generation = self.generation_store.generation_for(
                        snapshot_digest
                    )
                except GenerationStoreError as exc:
                    raise LearningCapabilityError(
                        "GENERATION_UNAVAILABLE"
                    ) from exc
                snapshot = LearningCapabilitySnapshot(
                    generation=generation,
                    capabilities=states,
                )
                snapshot.to_dict()
                return snapshot
            raise LearningCapabilityError(
                "AUTHORITY_CHANGED_DURING_SNAPSHOT"
            )
        except LearningCapabilityError:
            raise
        except AuthorityReadError as exc:
            raise LearningCapabilityError("AUTHORITY_UNREACHABLE") from exc
        except ValueError as exc:
            raise LearningCapabilityError("CONTRACT_MISMATCH") from exc
        except Exception as exc:
            raise LearningCapabilityError("INTERNAL_ERROR") from exc
