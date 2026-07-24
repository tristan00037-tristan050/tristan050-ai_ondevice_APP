# Storage-risk release gate

`storage_risk_acceptance_FS_v2_3.json` is intentionally unsigned. It is not an accepted exception.
The release owner must return the exact decision, its detached Ed25519 signature, and the public key.
The public key is then pinned as the only key in `storage_risk_allowed_signers` under the principal
`butler-storage-risk-owner`. The private key must never enter this repository or a build artifact.

Until the three owner artifacts exist and `verify_storage_risk_acceptance.py` passes, the title and
FTS plaintext finding remains open and all merge/release gates remain fail-closed.
