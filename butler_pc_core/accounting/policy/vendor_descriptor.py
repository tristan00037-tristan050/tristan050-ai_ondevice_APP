"""Canonical vendor-descriptor tokenization — the ONE normalization + HMAC that both the approved
vendor-descriptor registry and any consumer (e.g. the stage-3 shadow) must use.

A descriptor's ``normalized_exact_value_hmac`` = HMAC-SHA256(key, normalize(raw_vendor)) where the
key is derived from the policy profile id. Producing a registry entry and matching a live
transaction therefore use the identical function, so a pre-inserted placeholder is never needed —
the same raw string yields the same 64-hex token on both sides.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize_vendor_descriptor(text: object) -> str:
    """Deterministic normalization applied before hashing (NFKC · casefold · collapse ws · strip)."""
    s = unicodedata.normalize("NFKC", str(text if text is not None else ""))
    s = _WS.sub(" ", s).strip().casefold()
    return s


def _key(policy_profile_id: str) -> bytes:
    return hashlib.sha256(f"butler.box5.vendor_descriptor.v1:{policy_profile_id}".encode("utf-8")).digest()


def descriptor_hmac(text: object, *, policy_profile_id: str) -> str:
    """64-hex HMAC of the normalized vendor descriptor, keyed by the policy profile id."""
    normalized = normalize_vendor_descriptor(text)
    return hmac.new(_key(policy_profile_id), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
