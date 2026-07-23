# Box5 A4 key-material boundary v5.5

## Python independent verifier input

The producer may send the following four 32-byte tenant tokenization keys, plus
their schema, tenant, and key identifiers:

| Field | Purpose |
|---|---|
| `own_account_key_b64` | Tokenize the registered company account identity. |
| `bank_reference_key_b64` | Tokenize exact bank reference values. |
| `counterparty_account_key_b64` | Tokenize counterparty account identities. |
| `run_transaction_key_b64` | Tokenize transaction identities within a run. |

Both the producer boundary and the independent verifier require the exact field
set. Any additional field results in `BLOCK_TRUST_UNAVAILABLE`.

## Native-only signing authority

The independent Python verifier does not receive the 32-byte Ed25519 attestation
signing seed. Only the native Swift XPC authority reads that seed from Keychain,
constructs the CryptoKit private key, and signs the canonical receipt. A producer
material object containing `verification_signing_seed_b64`, or any other extra
field, is rejected before authority verification.

The raw `Data` buffer loaded from Keychain is registered for C-based zeroization
with `defer` immediately after loading, so normal completion, key-construction
failure, signature failure, and early return all execute the zeroizer. This is a
bounded claim: it does not prove erasure of CryptoKit internals, allocator copies,
kernel memory, swap, crash dumps, or every process-memory copy.
