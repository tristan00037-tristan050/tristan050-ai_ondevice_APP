use std::collections::BTreeSet;

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use chrono::{DateTime, Utc};
use ring::signature::{UnparsedPublicKey, ED25519};
use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};

use super::state::{
    canonical, canonical_without_signatures, is_oid, is_sha256, sha256, TrustedState,
    VerifyAndCommitRequest, COMMAND_SCHEMA,
};

const MAX_DOCUMENT_BYTES: usize = 256 * 1024;
const MAX_SIGNATURES: usize = 16;
const MAX_KEYS: usize = 32;
const DOMAIN: &[u8] = b"BUTLER-FIRSTSCREEN-SIGNED\0";

#[derive(Debug)]
struct StrictValue(Value);

impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct StrictVisitor;
        impl<'de> Visitor<'de> for StrictVisitor {
            type Value = Value;
            fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                formatter.write_str("strict JSON")
            }
            fn visit_bool<E: de::Error>(self, value: bool) -> Result<Value, E> {
                Ok(Value::Bool(value))
            }
            fn visit_i64<E: de::Error>(self, value: i64) -> Result<Value, E> {
                Ok(Value::Number(Number::from(value)))
            }
            fn visit_u64<E: de::Error>(self, value: u64) -> Result<Value, E> {
                Ok(Value::Number(Number::from(value)))
            }
            fn visit_f64<E: de::Error>(self, _value: f64) -> Result<Value, E> {
                Err(E::custom("floating point forbidden"))
            }
            fn visit_str<E: de::Error>(self, value: &str) -> Result<Value, E> {
                Ok(Value::String(value.to_owned()))
            }
            fn visit_string<E: de::Error>(self, value: String) -> Result<Value, E> {
                Ok(Value::String(value))
            }
            fn visit_none<E: de::Error>(self) -> Result<Value, E> {
                Ok(Value::Null)
            }
            fn visit_unit<E: de::Error>(self) -> Result<Value, E> {
                Ok(Value::Null)
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<Value, A::Error> {
                let mut values = Vec::new();
                while let Some(value) = sequence.next_element::<StrictValue>()? {
                    values.push(value.0);
                }
                Ok(Value::Array(values))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut access: A) -> Result<Value, A::Error> {
                let mut values = Map::new();
                while let Some((key, value)) = access.next_entry::<String, StrictValue>()? {
                    if values.insert(key, value.0).is_some() {
                        return Err(de::Error::custom("duplicate key"));
                    }
                }
                Ok(Value::Object(values))
            }
        }
        deserializer.deserialize_any(StrictVisitor).map(StrictValue)
    }
}

#[derive(Clone, Debug)]
pub struct VerifiedThreshold {
    pub valid_signer_ids: Vec<String>,
    pub rejected_envelope_count: usize,
    pub payload_digest: String,
}

#[derive(Clone, Debug)]
pub struct VerifiedUpdate {
    pub root_canonical: String,
    pub root_digest: String,
    pub root_version: u64,
    pub old_root_digest: Option<String>,
    pub valid_old_root_signer_ids: Vec<String>,
    pub valid_new_root_signer_ids: Vec<String>,
    pub revocations_canonical: String,
    pub revocation_digest: String,
    pub revocation_version: u64,
    pub valid_revocation_signer_ids: Vec<String>,
}

fn parse(raw: &str) -> Result<Value, &'static str> {
    if raw.is_empty()
        || raw.len() > MAX_DOCUMENT_BYTES
        || raw.as_bytes().starts_with(&[0xef, 0xbb, 0xbf])
    {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    let mut deserializer = serde_json::Deserializer::from_str(raw);
    let value = StrictValue::deserialize(&mut deserializer)
        .map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?
        .0;
    deserializer
        .end()
        .map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?;
    value.as_object().ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    Ok(value)
}

fn object(value: &Value) -> Result<&Map<String, Value>, &'static str> {
    value.as_object().ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")
}

fn exact(value: &Value, fields: &[&str]) -> Result<(), &'static str> {
    let actual: BTreeSet<&str> = object(value)?.keys().map(String::as_str).collect();
    let expected: BTreeSet<&str> = fields.iter().copied().collect();
    if actual != expected {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    Ok(())
}

fn string<'a>(value: &'a Value, field: &str) -> Result<&'a str, &'static str> {
    value
        .get(field)
        .and_then(Value::as_str)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")
}

fn version(value: &Value) -> Result<u64, &'static str> {
    let result = value
        .get("version")
        .and_then(Value::as_u64)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    if result == 0 {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    Ok(result)
}

fn check_time(value: &Value, field: &str, future_is_error: bool) -> Result<(), &'static str> {
    let parsed = DateTime::parse_from_rfc3339(string(value, field)?)
        .map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?
        .with_timezone(&Utc);
    if (future_is_error && parsed > Utc::now()) || (!future_is_error && parsed <= Utc::now()) {
        return Err("BLOCK_ROOT_EXPIRED");
    }
    Ok(())
}

fn signatures(value: &Value) -> Result<&Vec<Value>, &'static str> {
    let values = value
        .get("signatures")
        .and_then(Value::as_array)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    if values.is_empty() || values.len() > MAX_SIGNATURES {
        return Err("BLOCK_SIGNATURE_THRESHOLD");
    }
    Ok(values)
}

fn role<'a>(root: &'a Value, name: &str) -> Result<&'a Value, &'static str> {
    root.get("roles")
        .and_then(Value::as_object)
        .and_then(|roles| roles.get(name))
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")
}

fn verify_threshold(
    document_type: &str,
    document: &Value,
    keys: &Map<String, Value>,
    role_value: &Value,
    revoked: &BTreeSet<String>,
    error: &'static str,
) -> Result<VerifiedThreshold, &'static str> {
    exact(role_value, &["key_ids", "threshold"])?;
    let allowed: BTreeSet<String> = role_value
        .get("key_ids")
        .and_then(Value::as_array)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?
        .iter()
        .map(|item| {
            item.as_str()
                .map(str::to_owned)
                .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")
        })
        .collect::<Result<_, _>>()?;
    let threshold = role_value
        .get("threshold")
        .and_then(Value::as_u64)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")? as usize;
    if threshold == 0 || threshold > allowed.len() {
        return Err(error);
    }
    let schema = string(document, "schema_version")?;
    let payload = canonical_without_signatures(document)?;
    let payload_digest = sha256(&payload);
    let mut message =
        Vec::with_capacity(DOMAIN.len() + document_type.len() + schema.len() + payload.len() + 2);
    message.extend_from_slice(DOMAIN);
    message.extend_from_slice(document_type.as_bytes());
    message.push(0);
    message.extend_from_slice(schema.as_bytes());
    message.push(0);
    message.extend_from_slice(&payload);
    let mut valid = BTreeSet::new();
    let mut rejected = 0;
    for envelope in signatures(document)? {
        exact(envelope, &["key_id", "signature"])?;
        let key_id = string(envelope, "key_id")?;
        if valid.contains(key_id) || !allowed.contains(key_id) || revoked.contains(key_id) {
            rejected += 1;
            continue;
        }
        let Some(key) = keys.get(key_id) else {
            rejected += 1;
            continue;
        };
        exact(key, &["algorithm", "public_key"])?;
        if string(key, "algorithm")? != "ed25519" {
            rejected += 1;
            continue;
        }
        let public = URL_SAFE_NO_PAD
            .decode(string(key, "public_key")?)
            .map_err(|_| error)?;
        let signature = URL_SAFE_NO_PAD
            .decode(string(envelope, "signature")?)
            .map_err(|_| error)?;
        if public.len() != 32 || signature.len() != 64 {
            rejected += 1;
            continue;
        }
        if UnparsedPublicKey::new(&ED25519, public)
            .verify(&message, &signature)
            .is_ok()
        {
            valid.insert(key_id.to_owned());
        } else {
            rejected += 1;
        }
    }
    if valid.len() < threshold {
        return Err(error);
    }
    Ok(VerifiedThreshold {
        valid_signer_ids: valid.into_iter().collect(),
        rejected_envelope_count: rejected,
        payload_digest,
    })
}

fn validate_root(root: &Value) -> Result<(), &'static str> {
    exact(
        root,
        &[
            "schema_version",
            "policy_id",
            "version",
            "expires_at_utc",
            "consistent_snapshot",
            "keys",
            "roles",
            "previous_root_digest",
            "signatures",
        ],
    )?;
    if string(root, "schema_version")? != "butler.firstscreen.root-policy.v1"
        || string(root, "policy_id")? != "butler-firstscreen-trust"
        || root.get("consistent_snapshot") != Some(&Value::Bool(true))
    {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    version(root)?;
    check_time(root, "expires_at_utc", false)?;
    let keys = root
        .get("keys")
        .and_then(Value::as_object)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    if keys.is_empty() || keys.len() > MAX_KEYS {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    for (key_id, key) in keys {
        exact(key, &["algorithm", "public_key"])?;
        let public = URL_SAFE_NO_PAD
            .decode(string(key, "public_key")?)
            .map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?;
        if string(key, "algorithm")? != "ed25519"
            || public.len() != 32
            || format!("ed25519.{}", sha256(&public)) != *key_id
        {
            return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
        }
    }
    let roles = root
        .get("roles")
        .and_then(Value::as_object)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let actual_roles: BTreeSet<&str> = roles.keys().map(String::as_str).collect();
    let required_roles: BTreeSet<&str> = ["root", "risk-decision", "revocation", "release"]
        .into_iter()
        .collect();
    if actual_roles != required_roles {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    for name in required_roles {
        role(root, name)?;
    }
    Ok(())
}

fn string_set(value: &Value, field: &str) -> Result<BTreeSet<String>, &'static str> {
    value
        .get(field)
        .and_then(Value::as_array)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?
        .iter()
        .map(|item| {
            item.as_str()
                .map(str::to_owned)
                .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")
        })
        .collect()
}

fn u64_set(value: &Value, field: &str) -> Result<BTreeSet<u64>, &'static str> {
    value
        .get(field)
        .and_then(Value::as_array)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?
        .iter()
        .map(|item| item.as_u64().ok_or("BLOCK_NATIVE_TRUST_VERIFICATION"))
        .collect()
}

pub fn verify_update(
    request: &VerifyAndCommitRequest,
    current: Option<&TrustedState>,
) -> Result<VerifiedUpdate, &'static str> {
    if request.schema_version != COMMAND_SCHEMA
        || !matches!(request.environment.as_str(), "development" | "release")
        || !is_oid(&request.source_commit_oid)
        || !is_oid(&request.source_tree_oid)
        || !is_sha256(&request.native_build_identity_digest)
        || request.request_id.is_empty()
    {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    let embedded_build_digest =
        option_env!("BUTLER_BUILD_CONTEXT_DIGEST").ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let embedded_commit =
        option_env!("BUTLER_SOURCE_COMMIT_OID").ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let embedded_tree =
        option_env!("BUTLER_SOURCE_TREE_OID").ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    if embedded_build_digest != request.native_build_identity_digest
        || embedded_commit != request.source_commit_oid
        || embedded_tree != request.source_tree_oid
    {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    let root = parse(&request.root_json)?;
    validate_root(&root)?;
    let root_keys = root
        .get("keys")
        .and_then(Value::as_object)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let empty = BTreeSet::new();
    let new_threshold = verify_threshold(
        "root-policy",
        &root,
        root_keys,
        role(&root, "root")?,
        &empty,
        "BLOCK_ROOT_NEW_THRESHOLD",
    )?;
    debug_assert!(new_threshold.rejected_envelope_count <= MAX_SIGNATURES);
    let root_digest = new_threshold.payload_digest.clone();
    let root_version = version(&root)?;
    let (old_root_digest, valid_old_root_signer_ids) = match current {
        None => {
            if request.expected_generation != 0
                || root_version != 1
                || !root.get("previous_root_digest").is_some_and(Value::is_null)
            {
                return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
            }
            let anchor = option_env!("BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256")
                .ok_or("BLOCK_ROOT_BOOTSTRAP_ANCHOR")?;
            if !is_sha256(anchor) || anchor != root_digest {
                return Err("BLOCK_ROOT_BOOTSTRAP_ANCHOR");
            }
            (None, Vec::new())
        }
        Some(state) => {
            if request.expected_generation != state.generation {
                return Err("BLOCK_TRUST_STATE_CAS");
            }
            let old_root = parse(&state.current_root_canonical)?;
            validate_root(&old_root)?;
            if root_version == state.root_version {
                if root_digest != state.root_digest {
                    return Err("BLOCK_ROOT_VERSION_SEQUENCE");
                }
                (
                    Some(state.root_digest.clone()),
                    state.valid_root_signer_ids.clone(),
                )
            } else {
                if root_version != state.root_version + 1 {
                    return Err("BLOCK_ROOT_VERSION_SEQUENCE");
                }
                if root.get("previous_root_digest").and_then(Value::as_str)
                    != Some(state.root_digest.as_str())
                {
                    return Err("BLOCK_ROOT_PREVIOUS_DIGEST");
                }
                let old_keys = old_root
                    .get("keys")
                    .and_then(Value::as_object)
                    .ok_or("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?;
                let old = verify_threshold(
                    "root-policy",
                    &root,
                    old_keys,
                    role(&old_root, "root")?,
                    &empty,
                    "BLOCK_ROOT_OLD_THRESHOLD",
                )?;
                (Some(state.root_digest.clone()), old.valid_signer_ids)
            }
        }
    };

    let revocations = parse(&request.revocations_json)?;
    exact(
        &revocations,
        &[
            "schema_version",
            "policy_id",
            "version",
            "generated_at_utc",
            "expires_at_utc",
            "previous_digest",
            "root_policy_digest",
            "revoked_decision_ids",
            "revoked_key_ids",
            "revoked_epochs",
            "signatures",
        ],
    )?;
    if string(&revocations, "schema_version")? != "butler.firstscreen.revocations.v2"
        || string(&revocations, "policy_id")? != "butler-firstscreen-trust"
        || string(&revocations, "root_policy_digest")? != root_digest
    {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    check_time(&revocations, "generated_at_utc", true)?;
    check_time(&revocations, "expires_at_utc", false)?;
    let revocation_version = version(&revocations)?;
    if let Some(state) = current {
        if revocation_version < state.revocation_version
            || (revocation_version == state.revocation_version
                && sha256(&canonical_without_signatures(&revocations)?) != state.revocation_digest)
            || (revocation_version > state.revocation_version
                && (revocation_version != state.revocation_version + 1
                    || revocations.get("previous_digest").and_then(Value::as_str)
                        != Some(state.revocation_digest.as_str())))
        {
            return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
        }
    } else if revocation_version != 1
        || !revocations
            .get("previous_digest")
            .is_some_and(Value::is_null)
    {
        return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
    }
    let revocation_threshold = verify_threshold(
        "revocations",
        &revocations,
        root_keys,
        role(&root, "revocation")?,
        &empty,
        "BLOCK_REVOCATION_THRESHOLD",
    )?;
    debug_assert!(revocation_threshold.rejected_envelope_count <= MAX_SIGNATURES);
    let revoked_decisions = string_set(&revocations, "revoked_decision_ids")?;
    let revoked = string_set(&revocations, "revoked_key_ids")?;
    let revoked_epochs = u64_set(&revocations, "revoked_epochs")?;
    if let Some(state) = current {
        let previous = parse(&state.current_revocations_canonical)?;
        if !string_set(&previous, "revoked_decision_ids")?.is_subset(&revoked_decisions)
            || !string_set(&previous, "revoked_key_ids")?.is_subset(&revoked)
            || !u64_set(&previous, "revoked_epochs")?.is_subset(&revoked_epochs)
        {
            return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
        }
    }

    let decision = parse(&request.decision_json)?;
    exact(
        &decision,
        &[
            "schema_version",
            "policy_id",
            "decision_id",
            "version",
            "approved_at_utc",
            "expires_at_utc",
            "scope",
            "protection_boundary",
            "data_classification",
            "owner_role",
            "revocation_epoch",
            "root_policy_digest",
            "source_blob_digest",
            "canonical_ssot_location",
            "signatures",
        ],
    )?;
    if string(&decision, "schema_version")? != "butler.firstscreen.risk-decision.v2"
        || string(&decision, "policy_id")? != "butler-firstscreen-trust"
        || string(&decision, "root_policy_digest")? != root_digest
    {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    check_time(&decision, "approved_at_utc", true)?;
    check_time(&decision, "expires_at_utc", false)?;
    verify_threshold(
        "risk-decision",
        &decision,
        root_keys,
        role(&root, "risk-decision")?,
        &revoked,
        "BLOCK_SIGNATURE_THRESHOLD",
    )?;
    let decision_epoch = decision
        .get("revocation_epoch")
        .and_then(Value::as_u64)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    if revoked_decisions.contains(string(&decision, "decision_id")?)
        || revoked_epochs.contains(&decision_epoch)
    {
        return Err("BLOCK_SIGNATURE_THRESHOLD");
    }

    let release = parse(&request.release_subjects_json)?;
    exact(
        &release,
        &[
            "schema_version",
            "policy_id",
            "build_context_digest",
            "subjects",
            "created_at_utc",
            "signatures",
        ],
    )?;
    if string(&release, "schema_version")? != "butler.firstscreen.release-subjects.v1"
        || string(&release, "policy_id")? != "butler-firstscreen-trust"
        || string(&release, "build_context_digest")? != request.native_build_identity_digest
    {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    let subjects = release
        .get("subjects")
        .and_then(Value::as_object)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let subject_names: BTreeSet<&str> = subjects.keys().map(String::as_str).collect();
    if subject_names
        != [
            "source_archive",
            "web_dist_archive",
            "macos_artifact",
            "sbom",
        ]
        .into_iter()
        .collect()
    {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    for subject in subjects.values() {
        exact(subject, &["name", "size", "sha256", "build_context_digest"])?;
        if !is_sha256(string(subject, "sha256")?)
            || string(subject, "build_context_digest")? != request.native_build_identity_digest
            || subject
                .get("size")
                .and_then(Value::as_u64)
                .is_none_or(|size| size == 0)
        {
            return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
        }
    }
    check_time(&release, "created_at_utc", true)?;
    verify_threshold(
        "release-subjects",
        &release,
        root_keys,
        role(&root, "release")?,
        &revoked,
        "BLOCK_SIGNATURE_THRESHOLD",
    )?;

    Ok(VerifiedUpdate {
        root_canonical: String::from_utf8(canonical(&root)?)
            .map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?,
        root_digest,
        root_version,
        old_root_digest,
        valid_old_root_signer_ids,
        valid_new_root_signer_ids: new_threshold.valid_signer_ids,
        revocations_canonical: String::from_utf8(canonical(&revocations)?)
            .map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?,
        revocation_digest: revocation_threshold.payload_digest,
        revocation_version,
        valid_revocation_signer_ids: revocation_threshold.valid_signer_ids,
    })
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{string_set, u64_set};

    #[test]
    fn revocation_epoch_set_accepts_only_unsigned_integers() {
        let valid = json!({"revoked_epochs": [0, 7, 42]});
        assert_eq!(u64_set(&valid, "revoked_epochs").unwrap().len(), 3);

        for malformed in [
            json!({"revoked_epochs": ["7"]}),
            json!({"revoked_epochs": [-1]}),
            json!({"revoked_epochs": [true]}),
        ] {
            assert_eq!(
                u64_set(&malformed, "revoked_epochs"),
                Err("BLOCK_NATIVE_TRUST_VERIFICATION")
            );
        }
    }

    #[test]
    fn revocation_decision_ids_reject_non_strings() {
        let malformed = json!({"revoked_decision_ids": ["decision-1", 7]});
        assert_eq!(
            string_set(&malformed, "revoked_decision_ids"),
            Err("BLOCK_NATIVE_TRUST_VERIFICATION")
        );
    }
}
