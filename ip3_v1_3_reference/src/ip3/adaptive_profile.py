from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping
from .privacy import canonical_digest

@dataclass(frozen=True)
class UserRoutingProfile:
    profile_digest: str
    local_success_count: int
    central_success_count: int
    blocked_count: int
    privacy_mode: bool = True


def update_profile(profile: UserRoutingProfile | None, decision: Mapping[str, object]) -> UserRoutingProfile:
    base = profile or UserRoutingProfile(profile_digest="0" * 64, local_success_count=0, central_success_count=0, blocked_count=0, privacy_mode=True)
    target = str(decision.get("target", "blocked"))
    local = base.local_success_count + (1 if target.startswith("local") else 0)
    central = base.central_success_count + (1 if target == "central_server" else 0)
    blocked = base.blocked_count + (1 if target == "blocked" else 0)
    payload = {"local": local, "central": central, "blocked": blocked, "privacy_mode": True}
    return UserRoutingProfile(profile_digest=canonical_digest(payload), local_success_count=local, central_success_count=central, blocked_count=blocked, privacy_mode=True)
