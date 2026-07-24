use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const STATE_SCHEMA: &str = "butler.firstscreen.trusted-state.v3";
pub const RECEIPT_SCHEMA: &str = "butler.firstscreen.native-trust-receipt.v2";
pub const COMMAND_SCHEMA: &str = "butler.firstscreen.verify-and-commit.v2";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrustedState {
    pub schema_version: String,
    pub policy_id: String,
    pub environment: String,
    pub generation: u64,
    pub current_root_canonical: String,
    pub root_digest: String,
    pub root_version: u64,
    pub current_revocations_canonical: String,
    pub revocation_digest: String,
    pub revocation_version: u64,
    pub valid_root_signer_ids: Vec<String>,
    pub valid_revocation_signer_ids: Vec<String>,
    pub source_commit_oid: String,
    pub source_tree_oid: String,
    pub native_build_identity_digest: String,
    pub previous_trusted_state_receipt_digest: Option<String>,
    pub committed_at_utc: String,
    pub runtime_activation_allowed: bool,
}

#[derive(Clone, Debug, Serialize)]
struct StateCommitProjection<'a> {
    schema_version: &'a str,
    policy_id: &'a str,
    environment: &'a str,
    generation: u64,
    current_root_canonical: &'a str,
    root_digest: &'a str,
    root_version: u64,
    current_revocations_canonical: &'a str,
    revocation_digest: &'a str,
    revocation_version: u64,
    valid_root_signer_ids: &'a [String],
    valid_revocation_signer_ids: &'a [String],
    source_commit_oid: &'a str,
    source_tree_oid: &'a str,
    native_build_identity_digest: &'a str,
    committed_at_utc: &'a str,
    runtime_activation_allowed: bool,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VerifyAndCommitRequest {
    pub schema_version: String,
    pub request_id: String,
    pub expected_generation: u64,
    pub environment: String,
    pub root_json: String,
    pub revocations_json: String,
    pub decision_json: String,
    pub release_subjects_json: String,
    pub source_commit_oid: String,
    pub source_tree_oid: String,
    pub native_build_identity_digest: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct NativeTrustReceipt {
    pub schema_version: &'static str,
    pub request_id: String,
    pub status: &'static str,
    pub error_code: &'static str,
    pub generation_before: u64,
    pub generation_after: u64,
    pub old_root_digest: Option<String>,
    pub new_root_digest: String,
    pub root_version: u64,
    pub revocation_digest: String,
    pub revocation_version: u64,
    pub valid_old_root_signer_ids: Vec<String>,
    pub valid_new_root_signer_ids: Vec<String>,
    pub valid_revocation_signer_ids: Vec<String>,
    pub rejected_envelope_count: usize,
    pub rejected_envelope_reasons: Vec<String>,
    pub source_commit_oid: String,
    pub source_tree_oid: String,
    pub native_build_identity_digest: String,
    pub committed_state_digest: String,
    pub previous_receipt_digest: Option<String>,
    pub issued_at_utc: String,
    pub runtime_activation_allowed: bool,
    pub receipt_digest: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct RuntimeTrustStatus {
    pub schema_version: &'static str,
    pub authority: &'static str,
    pub configured: bool,
    pub generation: u64,
    pub root_digest: Option<String>,
    pub root_version: Option<u64>,
    pub revocation_digest: Option<String>,
    pub revocation_version: Option<u64>,
    pub previous_trusted_state_receipt_digest: Option<String>,
    pub runtime_activation_allowed: bool,
}

pub fn canonical<T: Serialize>(value: &T) -> Result<Vec<u8>, &'static str> {
    fn sorted(value: serde_json::Value) -> serde_json::Value {
        match value {
            serde_json::Value::Object(object) => {
                let mut entries: Vec<_> = object.into_iter().collect();
                entries.sort_by(|left, right| left.0.as_bytes().cmp(right.0.as_bytes()));
                serde_json::Value::Object(
                    entries
                        .into_iter()
                        .map(|(key, value)| (key, sorted(value)))
                        .collect(),
                )
            }
            serde_json::Value::Array(values) => {
                serde_json::Value::Array(values.into_iter().map(sorted).collect())
            }
            scalar => scalar,
        }
    }
    let value = serde_json::to_value(value).map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?;
    serde_json::to_vec(&sorted(value)).map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")
}

pub fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

pub fn is_oid(value: &str) -> bool {
    matches!(value.len(), 40 | 64)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

pub fn state_commit_projection(state: &TrustedState) -> Result<Vec<u8>, &'static str> {
    canonical(&StateCommitProjection {
        schema_version: &state.schema_version,
        policy_id: &state.policy_id,
        environment: &state.environment,
        generation: state.generation,
        current_root_canonical: &state.current_root_canonical,
        root_digest: &state.root_digest,
        root_version: state.root_version,
        current_revocations_canonical: &state.current_revocations_canonical,
        revocation_digest: &state.revocation_digest,
        revocation_version: state.revocation_version,
        valid_root_signer_ids: &state.valid_root_signer_ids,
        valid_revocation_signer_ids: &state.valid_revocation_signer_ids,
        source_commit_oid: &state.source_commit_oid,
        source_tree_oid: &state.source_tree_oid,
        native_build_identity_digest: &state.native_build_identity_digest,
        committed_at_utc: &state.committed_at_utc,
        runtime_activation_allowed: state.runtime_activation_allowed,
    })
}

pub fn committed_state_digest(state: &TrustedState) -> Result<String, &'static str> {
    Ok(sha256(&state_commit_projection(state)?))
}

pub fn validate_state(state: &TrustedState) -> Result<(), &'static str> {
    if state.schema_version != STATE_SCHEMA
        || state.policy_id != "butler-firstscreen-trust"
        || !matches!(state.environment.as_str(), "development" | "release")
        || state.generation == 0
        || state.root_version == 0
        || state.revocation_version == 0
        || state.runtime_activation_allowed
        || !is_sha256(&state.root_digest)
        || !is_sha256(&state.revocation_digest)
        || !is_sha256(&state.native_build_identity_digest)
        || !is_oid(&state.source_commit_oid)
        || !is_oid(&state.source_tree_oid)
        || state.previous_trusted_state_receipt_digest.is_none()
        || state.valid_root_signer_ids.is_empty()
        || state.valid_revocation_signer_ids.is_empty()
        || state
            .valid_root_signer_ids
            .iter()
            .collect::<std::collections::BTreeSet<_>>()
            .len()
            != state.valid_root_signer_ids.len()
        || state
            .valid_revocation_signer_ids
            .iter()
            .collect::<std::collections::BTreeSet<_>>()
            .len()
            != state.valid_revocation_signer_ids.len()
        || state
            .previous_trusted_state_receipt_digest
            .as_deref()
            .is_some_and(|value| !is_sha256(value))
    {
        return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
    }
    let root: serde_json::Value = serde_json::from_str(&state.current_root_canonical)
        .map_err(|_| "BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?;
    let revocations: serde_json::Value = serde_json::from_str(&state.current_revocations_canonical)
        .map_err(|_| "BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?;
    if canonical(&root)? != state.current_root_canonical.as_bytes()
        || canonical(&revocations)? != state.current_revocations_canonical.as_bytes()
        || sha256(&canonical_without_signatures(&root)?) != state.root_digest
        || sha256(&canonical_without_signatures(&revocations)?) != state.revocation_digest
        || root.get("version").and_then(serde_json::Value::as_u64) != Some(state.root_version)
        || revocations
            .get("version")
            .and_then(serde_json::Value::as_u64)
            != Some(state.revocation_version)
        || revocations
            .get("root_policy_digest")
            .and_then(serde_json::Value::as_str)
            != Some(state.root_digest.as_str())
    {
        return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
    }
    Ok(())
}

pub fn canonical_without_signatures(value: &serde_json::Value) -> Result<Vec<u8>, &'static str> {
    let mut unsigned = value.clone();
    unsigned
        .as_object_mut()
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?
        .remove("signatures");
    canonical(&unsigned)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn state(receipt: Option<&str>) -> TrustedState {
        TrustedState {
            schema_version: STATE_SCHEMA.into(),
            policy_id: "butler-firstscreen-trust".into(),
            environment: "development".into(),
            generation: 1,
            current_root_canonical: "{}".into(),
            root_digest: "1".repeat(64),
            root_version: 1,
            current_revocations_canonical: "{}".into(),
            revocation_digest: "2".repeat(64),
            revocation_version: 1,
            valid_root_signer_ids: vec!["root".into()],
            valid_revocation_signer_ids: vec!["revocation".into()],
            source_commit_oid: "3".repeat(40),
            source_tree_oid: "4".repeat(40),
            native_build_identity_digest: "5".repeat(64),
            previous_trusted_state_receipt_digest: receipt.map(str::to_owned),
            committed_at_utc: "2026-07-23T00:00:00Z".into(),
            runtime_activation_allowed: false,
        }
    }

    #[test]
    fn rs_trust_001_receipt_link_is_excluded_from_commit_projection() {
        let without_link = state(None);
        let with_link = state(Some(&"a".repeat(64)));
        assert_eq!(
            committed_state_digest(&without_link).unwrap(),
            committed_state_digest(&with_link).unwrap()
        );
        assert_ne!(
            sha256(&canonical(&without_link).unwrap()),
            sha256(&canonical(&with_link).unwrap())
        );
    }

    #[test]
    fn rs_trust_002_commit_projection_changes_for_authoritative_fields() {
        let baseline = state(None);
        let mut changed = baseline.clone();
        changed.generation += 1;
        assert_ne!(
            committed_state_digest(&baseline).unwrap(),
            committed_state_digest(&changed).unwrap()
        );
    }
}
