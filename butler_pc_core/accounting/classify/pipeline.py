"""Box 5 v3.2 deterministic stage-3 classifier."""

from __future__ import annotations

import re

from .models import (
    CanonicalTransactionV2,
    DecisionState,
    ReasonCode,
    UnverifiedClassificationDraft,
)
from .port import (
    PolicyPort,
    PolicyPortError,
    RuleBasis,
    RuleFacts,
    RuleSelectionReply,
    VendorMatchReply,
    VendorMatchState,
)


_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class Stage3Classifier:
    """Stateless Area-B classifier; it cannot issue or verify Authority receipts."""

    CONTRACT_VERSION = "butler.box5.stage3_classifier.v3.2"

    @staticmethod
    def _facts(tx: CanonicalTransactionV2, vendor_match_id: str | None) -> RuleFacts:
        return RuleFacts(
            direction=tx.direction,
            event_kind=tx.event_kind,
            vendor_match_id=vendor_match_id,
            purpose_code=tx.purpose_code,
            purpose_evidence_digest=tx.purpose_evidence_digest,
            description_feature_digests=tx.description_feature_digests,
            evidence_digests=tx.evidence_digests,
            service_period_start=tx.service_period_start.isoformat() if tx.service_period_start else None,
            service_period_end=tx.service_period_end.isoformat() if tx.service_period_end else None,
            accounting_period_end=tx.accounting_period_end.isoformat() if tx.accounting_period_end else None,
        )

    @staticmethod
    def _blocked(
        tx: CanonicalTransactionV2,
        reason: ReasonCode,
        *,
        exponent: int | None = None,
        transcript: str | None = None,
    ) -> UnverifiedClassificationDraft:
        return UnverifiedClassificationDraft(
            state=DecisionState.BLOCKED,
            reason_code=reason,
            transaction_digest=tx.transaction_digest,
            currency=tx.currency,
            currency_exponent=exponent,
            transcript_digest=transcript,
            blockers=(reason,),
        )

    @staticmethod
    def _review(
        tx: CanonicalTransactionV2,
        reason: ReasonCode,
        *,
        exponent: int,
        transcript: str,
        score_bp: int = 0,
    ) -> UnverifiedClassificationDraft:
        return UnverifiedClassificationDraft(
            state=DecisionState.REVIEW_REQUIRED,
            reason_code=reason,
            transaction_digest=tx.transaction_digest,
            currency=tx.currency,
            currency_exponent=exponent,
            transcript_digest=transcript,
            confidence_bp=score_bp,
            warnings=(reason,),
        )

    @staticmethod
    def _read_transcript(port: PolicyPort) -> str:
        digest = port.transcript_digest()
        if not isinstance(digest, str) or not _HEX_DIGEST_RE.fullmatch(digest):
            raise PolicyPortError(ReasonCode.BLOCK_TRANSCRIPT_MISMATCH)
        return digest

    def classify(
        self,
        tx: CanonicalTransactionV2,
        port: PolicyPort,
    ) -> UnverifiedClassificationDraft:
        """Produce an unverified draft from a session-bound Authority port.

        The main product must call Authority Finalize and VerifyReceipt before the
        draft can reach a journal proposal gate.
        """
        exponent: int | None = None
        try:
            exponent = port.currency_exponent(tx.currency, tx.currency_registry_version).exponent
            if tx.currency == "KRW" and exponent != 0:
                return self._blocked(
                    tx,
                    ReasonCode.BLOCK_CURRENCY_EXPONENT,
                    exponent=exponent,
                    transcript=self._read_transcript(port),
                )

            own_account = port.is_own_account(tx.counterparty_account_token)
            if not isinstance(own_account, bool):
                raise PolicyPortError(ReasonCode.BLOCK_AUTHORITY_BINDING)
            if own_account:
                return self._review(
                    tx,
                    ReasonCode.REVIEW_SELF_TRANSFER,
                    exponent=exponent,
                    transcript=self._read_transcript(port),
                )

            vendor = port.match_vendor_exact(tx.vendor_token)
            if not isinstance(vendor, VendorMatchReply):
                raise PolicyPortError(ReasonCode.BLOCK_AUTHORITY_BINDING)
            if vendor.state is VendorMatchState.AMBIGUOUS:
                return self._review(
                    tx,
                    ReasonCode.REVIEW_CLASSIFICATION_AMBIGUOUS,
                    exponent=exponent,
                    transcript=self._read_transcript(port),
                )

            selection = port.select_rule(
                self._facts(
                    tx,
                    vendor.match_id if vendor.state is VendorMatchState.EXACT else None,
                )
            )
            if not isinstance(selection, RuleSelectionReply):
                raise PolicyPortError(ReasonCode.BLOCK_AUTHORITY_BINDING)
            return self._from_selection(tx, port, exponent, selection)
        except PolicyPortError as exc:
            return self._blocked(tx, exc.reason_code, exponent=exponent)
        except Exception:
            return self._blocked(tx, ReasonCode.BLOCK_AUTHORITY_BINDING, exponent=exponent)

    def _from_selection(
        self,
        tx: CanonicalTransactionV2,
        port: PolicyPort,
        exponent: int,
        selection: RuleSelectionReply,
    ) -> UnverifiedClassificationDraft:
        if selection.basis is RuleBasis.BLOCKED:
            reason = selection.block_reason or ReasonCode.BLOCK_POLICY_CLOSURE
            return self._blocked(
                tx,
                reason,
                exponent=exponent,
                transcript=self._read_transcript(port),
            )
        if selection.basis in {RuleBasis.AMBIGUOUS, RuleBasis.NON_ACCOUNT_EVENT}:
            reason = (
                ReasonCode.REVIEW_NON_ACCOUNT_EVENT
                if selection.basis is RuleBasis.NON_ACCOUNT_EVENT
                else ReasonCode.REVIEW_CLASSIFICATION_AMBIGUOUS
            )
            return self._review(
                tx,
                reason,
                exponent=exponent,
                transcript=self._read_transcript(port),
                score_bp=selection.score_bp,
            )
        if selection.basis is RuleBasis.NO_MATCH:
            return self._review(
                tx,
                ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT,
                exponent=exponent,
                transcript=self._read_transcript(port),
            )
        if selection.basis is RuleBasis.STATISTICAL:
            return self._review(
                tx,
                ReasonCode.REVIEW_CLASSIFICATION_AMBIGUOUS,
                exponent=exponent,
                transcript=self._read_transcript(port),
                score_bp=min(selection.score_bp, 9_999),
            )
        if selection.basis is not RuleBasis.EXACT_DETERMINISTIC:
            return self._blocked(
                tx,
                ReasonCode.BLOCK_POLICY_CLOSURE,
                exponent=exponent,
                transcript=self._read_transcript(port),
            )
        if not selection.evidence_complete:
            return self._review(
                tx,
                ReasonCode.REVIEW_EVIDENCE_INSUFFICIENT,
                exponent=exponent,
                transcript=self._read_transcript(port),
            )
        if (
            selection.account_id is None
            or selection.rule_id is None
            or selection.rule_digest is None
        ):
            return self._blocked(
                tx,
                ReasonCode.BLOCK_POLICY_CLOSURE,
                exponent=exponent,
                transcript=self._read_transcript(port),
            )
        known_account = port.is_known_account(selection.account_id)
        if not isinstance(known_account, bool):
            raise PolicyPortError(ReasonCode.BLOCK_AUTHORITY_BINDING)
        if not known_account:
            return self._blocked(
                tx,
                ReasonCode.BLOCK_POLICY_CLOSURE,
                exponent=exponent,
                transcript=self._read_transcript(port),
            )
        return UnverifiedClassificationDraft(
            state=DecisionState.AUTO_PROPOSE,
            reason_code=ReasonCode.AUTO_PROPOSE_EXACT_RULE,
            transaction_digest=tx.transaction_digest,
            currency=tx.currency,
            currency_exponent=exponent,
            transcript_digest=self._read_transcript(port),
            account_id=selection.account_id,
            rule_id=selection.rule_id,
            rule_digest=selection.rule_digest,
            confidence_bp=10_000,
        )
