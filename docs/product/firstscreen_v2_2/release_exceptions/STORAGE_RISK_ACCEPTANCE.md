# FirstScreen storage-risk record — invalidated

Decision ID: `STORAGE_RISK_FS_V2_1_001`

The ATLink representative accepted local plaintext storage of conversation titles and the title FTS
index on 2026-07-20. The decision expires on 2027-01-20. Message bodies remain AES-GCM encrypted;
the app-data owner/mode/symlink guards and fail-closed startup behavior are mandatory compensating
controls. The accepted unprotected threats are administrator/root access, same-user malware, an
unlocked device, and plaintext-title disclosure.

The adjacent JSON is retained only as historical evidence. Its `signature_digest` is a content
checksum that anyone can recompute, not a signature, so it cannot authorize a release exception.
The fail-closed v2.3 gate requires a detached Ed25519 signature and repository-pinned public key.

This decision closes only the title/FTS finding. It does not approve canonical-remote provenance,
signed macOS execution, VoiceOver evidence, runtime activation, or product release.
