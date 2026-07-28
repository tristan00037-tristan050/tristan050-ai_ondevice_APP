from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from butler_pc_core.company_fact.storage import CompanyFactStore
from butler_pc_core.company_policy.storage import CompanyFormatStore, PolicyStore
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore

from .consumer_bindings import ConsumerBindingStore
from .contracts import AuthorityProbe, lower_hex_digest


class AuthorityReadError(RuntimeError):
    pass


class LearningAuthority(Protocol):
    key: str

    def revision(self) -> str: ...

    def probe(self) -> AuthorityProbe: ...


def _combined_revision(store_revision: str, binding_revision: str) -> str:
    return lower_hex_digest(
        {
            "store_revision": store_revision,
            "binding_revision": binding_revision,
        }
    )


@dataclass
class CompanyPolicyAuthority:
    store: PolicyStore
    bindings: ConsumerBindingStore
    key: str = "company_rules"

    def revision(self) -> str:
        try:
            summary = self.store.capability_summary()
            return _combined_revision(summary.revision, self.bindings.revision())
        except Exception as exc:
            raise AuthorityReadError("COMPANY_POLICY_AUTHORITY_FAILED") from exc

    def probe(self) -> AuthorityProbe:
        try:
            summary = self.store.capability_summary()
            digests = (
                (summary.active_policy_digest,)
                if summary.active_policy_digest is not None
                else ()
            )
            bound = bool(digests) and self.bindings.is_bound(self.key, digests)
            probe = AuthorityProbe(
                key=self.key,
                available=True,
                registered=summary.active_count > 0,
                consumer_bound=bound,
                preview_only=False,
                revision=_combined_revision(
                    summary.revision,
                    self.bindings.revision(),
                ),
                evidence_digest=lower_hex_digest(
                    {
                        "active_count": summary.active_count,
                        "object_digests": digests,
                        "consumer_bound": bound,
                    }
                ),
            )
            probe.validate()
            return probe
        except AuthorityReadError:
            raise
        except Exception as exc:
            raise AuthorityReadError("COMPANY_POLICY_AUTHORITY_FAILED") from exc


@dataclass
class CompanyFactAuthority:
    store: CompanyFactStore
    bindings: ConsumerBindingStore
    key: str = "company_facts"

    def revision(self) -> str:
        try:
            summary = self.store.capability_summary()
            return _combined_revision(summary.revision, self.bindings.revision())
        except Exception as exc:
            raise AuthorityReadError("COMPANY_FACT_AUTHORITY_FAILED") from exc

    def probe(self) -> AuthorityProbe:
        try:
            summary = self.store.capability_summary()
            bound = bool(summary.active_fact_digests) and self.bindings.is_bound(
                self.key,
                summary.active_fact_digests,
            )
            probe = AuthorityProbe(
                key=self.key,
                available=True,
                registered=summary.active_count > 0,
                consumer_bound=bound,
                preview_only=False,
                revision=_combined_revision(
                    summary.revision,
                    self.bindings.revision(),
                ),
                evidence_digest=lower_hex_digest(
                    {
                        "active_count": summary.active_count,
                        "object_digests": summary.active_fact_digests,
                        "consumer_bound": bound,
                    }
                ),
            )
            probe.validate()
            return probe
        except Exception as exc:
            raise AuthorityReadError("COMPANY_FACT_AUTHORITY_FAILED") from exc


@dataclass
class CompanyFormatAuthority:
    store: CompanyFormatStore
    bindings: ConsumerBindingStore
    key: str = "company_formats"

    def revision(self) -> str:
        try:
            summary = self.store.capability_summary()
            return _combined_revision(
                summary.index_digest,
                self.bindings.revision(),
            )
        except Exception as exc:
            raise AuthorityReadError("COMPANY_FORMAT_AUTHORITY_FAILED") from exc

    def probe(self) -> AuthorityProbe:
        try:
            summary = self.store.capability_summary()
            bound = bool(summary.active_format_digests) and self.bindings.is_bound(
                self.key,
                summary.active_format_digests,
            )
            probe = AuthorityProbe(
                key=self.key,
                available=True,
                registered=summary.registered_count > 0,
                consumer_bound=bound,
                preview_only=False,
                revision=_combined_revision(
                    summary.index_digest,
                    self.bindings.revision(),
                ),
                evidence_digest=lower_hex_digest(
                    {
                        "active_count": summary.active_count,
                        "registered_count": summary.registered_count,
                        "object_digests": summary.format_digests,
                        "active_object_digests": summary.active_format_digests,
                        "consumer_bound": bound,
                    }
                ),
            )
            probe.validate()
            return probe
        except Exception as exc:
            raise AuthorityReadError("COMPANY_FORMAT_AUTHORITY_FAILED") from exc


@dataclass
class FolderLearningAuthority:
    store: LearningEventStore
    bindings: ConsumerBindingStore
    key: str = "folder_learning"

    def revision(self) -> str:
        try:
            summary = self.store.capability_summary()
            return _combined_revision(summary.revision, self.bindings.revision())
        except Exception as exc:
            raise AuthorityReadError("FOLDER_LEARNING_AUTHORITY_FAILED") from exc

    def probe(self) -> AuthorityProbe:
        try:
            summary = self.store.capability_summary()
            registered = summary.approved_count > 0
            bound = registered and self.bindings.is_bound(
                self.key,
                summary.event_digests,
            )
            preview_only = not registered and summary.candidate_count > 0
            probe = AuthorityProbe(
                key=self.key,
                available=True,
                registered=registered,
                consumer_bound=bound,
                preview_only=preview_only,
                revision=_combined_revision(
                    summary.revision,
                    self.bindings.revision(),
                ),
                evidence_digest=lower_hex_digest(
                    {
                        "candidate_count": summary.candidate_count,
                        "approved_count": summary.approved_count,
                        "event_digests": summary.event_digests,
                        "consumer_bound": bound,
                    }
                ),
            )
            probe.validate()
            return probe
        except Exception as exc:
            raise AuthorityReadError("FOLDER_LEARNING_AUTHORITY_FAILED") from exc
