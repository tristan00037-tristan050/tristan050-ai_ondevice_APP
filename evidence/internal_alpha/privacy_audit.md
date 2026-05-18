# Internal Alpha Privacy Audit

Status: MEASURED_ONLY_PLAN
Scope: Card 1 Internal Alpha authoritative measurement privacy boundary

## 1. Privacy objective

Internal Alpha authoritative measurement must evaluate manual suggestion usefulness without exporting or storing raw user text in evidence artifacts.

The measurement protocol uses digest16, sample_id, redaction class metadata, reviewer_id_digest, controlled labels, and aggregate metrics only.

## 2. Raw data boundary

Evidence artifacts must not contain:

- raw_text
- original_text
- source_text
- user_text
- raw document content
- company name in plain form
- person name in plain form
- email address
- phone number
- file path
- server address
- secret, token, credential, key

Allowed evidence fields:

- sample_id
- digest16
- sample_group
- stratum
- redaction_class
- reviewer_id_digest
- label
- adjudicated_label
- reason_code
- aggregate counts

## 3. Reviewer access boundary

Reviewers receive only:

- redacted sample display
- digest/sample identifiers
- suggestion summary with sensitive content removed
- label definitions
- reason code list

Reviewers must not receive raw plaintext or original file content through the measurement package.

## 4. Butler 3-tier isolation alignment

Personal device tier:

- no accumulation of authoritative measurement raw text
- temporary local review rendering may exist only inside the Internal Alpha client session
- raw text must not be copied into evidence artifacts

Team server tier:

- stores only team-scoped measurement metadata when allowed by Internal Alpha policy
- digest-only audit records
- no cross-team evidence mixing

Central server tier:

- aggregate counts only
- no raw user text
- no tenant-specific plaintext
- no reviewer free-text unless redacted and converted to controlled reason code

## 5. Audit log requirements

Every authoritative rating event must produce an audit record with:

- event_id
- sample_id
- sample_digest16
- reviewer_id_digest
- rating_label
- raw_text_seen=false
- created_at
- client_version
- policy_context

Audit logs must not contain raw sample text.

## 6. Privacy audit grep rules

The validation script must fail if any evidence file contains forbidden keys or obvious plaintext patterns.

Forbidden keys:

- raw_text
- original_text
- source_text
- user_text
- plaintext

Forbidden pattern classes:

- email-like strings
- phone-like strings
- secret/token-like strings
- absolute local file paths
- IPv4 addresses outside documented synthetic examples

## 7. Privacy audit output

The privacy audit must emit:

```json
{
  "ok": true,
  "raw_text_hits": 0,
  "forbidden_key_hits": 0,
  "pii_pattern_hits": 0,
  "external_transfer_claim": false,
  "evidence_mode": "digest16_or_metadata_only"
}
```

## 8. Honest limitation

This audit plan verifies evidence artifacts and reviewer package boundaries. It does not by itself prove that every future reviewer UI implementation is correct. The UI implementation must pass a separate local-only and digest-only review gate before collection begins.
