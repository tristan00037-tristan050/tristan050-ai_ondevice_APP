"""Policy preflight for /api/analyze/stream free-chat requests.

The middleware policy gate intentionally protects registered box/helper routes.
Free chat shares the same sidecar entrypoint but must fail closed before company
knowledge resolution, task budgeting, or LLM execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.company_policy.storage import PolicyLoadError, PolicyStore


FREE_CHAT_MODES = {None, "", "free", "0", 0}
KNOWN_CARD_MODES = {
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "new_draft",
    "draft_write",
    "accounting",
    "accounting_classify",
    "document_review",
    "form_convert",
    "request_parse",
    "external_form",
    "form_fill",
}


@dataclass(frozen=True)
class PolicyBootstrapState:
    ready: bool
    fail_class: str | None
    policy_digest: str | None


def normalize_card_mode(card_mode: Any) -> str:
    if card_mode is None:
        return ""
    return str(card_mode).strip()


def is_free_chat_mode(card_mode: Any) -> bool:
    normalized = normalize_card_mode(card_mode)
    return card_mode is None or normalized in {"", "free", "0"}


def is_known_card_mode(card_mode: Any) -> bool:
    if is_free_chat_mode(card_mode):
        return True
    return normalize_card_mode(card_mode) in KNOWN_CARD_MODES


def policy_bootstrap_state(store: PolicyStore | None = None) -> PolicyBootstrapState:
    try:
        active_policy = (store or PolicyStore()).load_active_policy()
    except PolicyLoadError:
        return PolicyBootstrapState(False, "POLICY_LOAD_FAILED", None)
    except Exception:
        return PolicyBootstrapState(False, "POLICY_LOAD_FAILED", None)
    if active_policy is None:
        return PolicyBootstrapState(False, "POLICY_BOOTSTRAP_REQUIRED", None)
    return PolicyBootstrapState(True, None, active_policy.policy_digest)
