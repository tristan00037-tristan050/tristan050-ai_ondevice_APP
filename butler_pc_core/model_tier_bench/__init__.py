"""Model-tier-B benchmark integration surface for the Butler product.

This package is the *only* product-side code the offline benchmark harness
(``bench/model_tier_b``) reaches. It contains:

- ``observer``: a passive, side-channel observation hook. When no observer is
  registered the hooks are inert; when one is registered it receives digest/count
  metadata only. Product responses are byte-identical whether an observer is
  registered or not — the hook never influences return values.
- ``product_adapter``: the canonical adapter exposing the six benchmark entrypoints,
  each of which reaches a real Box3 / DLP product function.

Nothing here changes existing product routing or behavior; it only *calls* existing
product functions and records that the call happened. RUNTIME_ACTIVATION_ALLOWED
stays 0 and no model execution occurs here (that is M3-only, owner-run).
"""
