"""Verified chart-of-accounts projection for user assignment."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

from butler_pc_core.accounting.policy.loader import PolicyBundleSnapshot, load_bundled_draft

from .domain import AssignmentError, sha256_json


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    account_id: str
    account_code: str | None
    display_name: str
    category_path: tuple[str, ...]
    node_kind: str
    assignable: bool
    disabled_reason: str | None
    sort_order: int

    def public_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "account_code": self.account_code,
            "display_name": self.display_name,
            "category_path": list(self.category_path),
            "node_kind": self.node_kind,
            "assignable": self.assignable,
            "disabled_reason": self.disabled_reason,
            "sort_order": self.sort_order,
        }


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    registry_digest: str
    overlay_digest: str
    entries: tuple[RegistryEntry, ...]

    @classmethod
    def bundled(cls) -> "RegistrySnapshot":
        snapshot = load_bundled_draft()
        return cls.from_policy(snapshot)

    @classmethod
    def from_policy(cls, snapshot: PolicyBundleSnapshot) -> "RegistrySnapshot":
        chart = snapshot.documents["CHART_UPSTREAM"]
        overlay = snapshot.documents["POSTING_OVERLAY_TEMPLATE"]
        decisions = {item["account_id"]: item for item in overlay["decisions"]}
        accounts = {item["account_id"]: item for item in chart["accounts"]}

        def path_for(account_id: str) -> tuple[str, ...]:
            path: list[str] = []
            current: str | None = account_id
            seen: set[str] = set()
            while current is not None:
                if current in seen or current not in accounts:
                    raise AssignmentError("REGISTRY_INVALID", 503, "The account registry graph is invalid.")
                seen.add(current)
                account = accounts[current]
                path.append(str(account["name_ko"]))
                current = account["parent_account_id"]
            return tuple(reversed(path))

        projected: list[RegistryEntry] = []
        for account in sorted(chart["accounts"], key=lambda item: item["display_order"]):
            decision = decisions.get(account["account_id"])
            if decision is None:
                raise AssignmentError("REGISTRY_INVALID", 503, "The account registry overlay is incomplete.")
            node_kind = str(decision["node_kind"])
            assignable = node_kind in {"POSTING", "CONTRA"} and decision["posting_allowed"] is True
            projected.append(
                RegistryEntry(
                    account_id=str(account["account_id"]),
                    account_code=account["code"],
                    display_name=str(account["name_ko"]),
                    category_path=path_for(str(account["account_id"])),
                    node_kind=node_kind,
                    assignable=assignable,
                    disabled_reason=None if assignable else f"ACCOUNT_NODE_{node_kind}_NOT_ASSIGNABLE",
                    sort_order=int(account["display_order"]),
                )
            )
        return cls(
            registry_digest=sha256_json([entry.public_dict() for entry in projected]),
            overlay_digest=sha256_json(_plain(overlay)),
            entries=tuple(projected),
        )

    def require_digest(self, expected: str) -> None:
        if expected != self.registry_digest:
            raise AssignmentError(
                "REGISTRY_STALE",
                409,
                "The account registry changed. Refresh before assigning.",
                actions=("REFRESH_ACCOUNT_REGISTRY",),
            )

    def require_assignable(self, account_id: str) -> RegistryEntry:
        for entry in self.entries:
            if entry.account_id == account_id:
                if not entry.assignable:
                    raise AssignmentError("ACCOUNT_NOT_ASSIGNABLE", 422, "This account cannot be assigned to a transaction.")
                return entry
        raise AssignmentError("ACCOUNT_UNKNOWN", 422, "The selected account does not exist.")

    def resolve_exact(self, value: object) -> RegistryEntry | None:
        if not isinstance(value, str):
            return None
        candidate = " ".join(value.strip().split())
        matches = [
            entry
            for entry in self.entries
            if candidate == entry.account_id
            or (entry.account_code is not None and candidate == entry.account_code)
            or candidate == " ".join(entry.display_name.strip().split())
        ]
        if len(matches) != 1 or not matches[0].assignable:
            return None
        return matches[0]

    def public_view(self, locale: str = "ko-KR") -> dict[str, Any]:
        payload = {
            "schema_version": "2.0",
            "registry_digest": self.registry_digest,
            "overlay_digest": self.overlay_digest,
            "locale": locale,
            "entries": [entry.public_dict() for entry in self.entries],
        }
        payload["etag"] = f'"{sha256_json(payload)}"'
        return payload
