use std::collections::{BTreeMap, BTreeSet};
use std::fs::{File, OpenOptions};
use std::io::Read;
use std::path::{Path, PathBuf};

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use chrono::{DateTime, Utc};
use ring::signature::{UnparsedPublicKey, ED25519};
use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};

use super::state::{canonical, canonical_without_signatures, is_oid, is_sha256, sha256, TrustedState, VerifyAndCommitRequest, COMMAND_SCHEMA};

const MAX_DOCUMENT_BYTES: usize = 256 * 1024;
const MAX_ARTIFACT_BYTES: u64 = 1024 * 1024 * 1024;
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
            fn visit_bool<E: de::Error>(self, value: bool) -> Result<Value, E> { Ok(Value::Bool(value)) }
            fn visit_i64<E: de::Error>(self, value: i64) -> Result<Value, E> { Ok(Value::Number(Number::from(value))) }
            fn visit_u64<E: de::Error>(self, value: u64) -> Result<Value, E> { Ok(Value::Number(Number::from(value))) }
            fn visit_f64<E: de::Error>(self, _value: f64) -> Result<Value, E> { Err(E::custom("floating point forbidden")) }
            fn visit_str<E: de::Error>(self, value: &str) -> Result<Value, E> { Ok(Value::String(value.to_owned())) }
            fn visit_string<E: de::Error>(self, value: String) -> Result<Value, E> { Ok(Value::String(value)) }
            fn visit_none<E: de::Error>(self) -> Result<Value, E> { Ok(Value::Null) }
            fn visit_unit<E: de::Error>(self) -> Result<Value, E> { Ok(Value::Null) }
            fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<Value, A::Error> {
                let mut values = Vec::new();
                while let Some(value) = sequence.next_element::<StrictValue>()? { values.push(value.0); }
                Ok(Value::Array(values))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut access: A) -> Result<Value, A::Error> {
                let mut values = Map::new();
                while let Some((key, value)) = access.next_entry::<String, StrictValue>()? {
                    if values.insert(key, value.0).is_some() { return Err(de::Error::custom("duplicate key")); }
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
    pub rejected_envelope_count: usize,
    pub rejected_envelope_reasons: Vec<String>,
}

fn parse(raw: &str) -> Result<Value, &'static str> {
    if raw.is_empty() || raw.len() > MAX_DOCUMENT_BYTES || raw.as_bytes().starts_with(&[0xef, 0xbb, 0xbf]) {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    let mut deserializer = serde_json::Deserializer::from_str(raw);
    let value = StrictValue::deserialize(&mut deserializer)
        .map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?.0;
    deserializer.end().map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?;
    value.as_object().ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    Ok(value)
}

fn object(value: &Value) -> Result<&Map<String, Value>, &'static str> {
    value.as_object().ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")
}

fn exact(value: &Value, fields: &[&str]) -> Result<(), &'static str> {
    let actual: BTreeSet<&str> = object(value)?.keys().map(String::as_str).collect();
    let expected: BTreeSet<&str> = fields.iter().copied().collect();
    if actual != expected { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    Ok(())
}

fn string<'a>(value: &'a Value, field: &str) -> Result<&'a str, &'static str> {
    value.get(field).and_then(Value::as_str).ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")
}

fn version(value: &Value) -> Result<u64, &'static str> {
    let result = value.get("version").and_then(Value::as_u64).ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    if result == 0 { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    Ok(result)
}

fn timestamp(value: &Value, field: &str) -> Result<DateTime<Utc>, &'static str> {
    DateTime::parse_from_rfc3339(string(value, field)?)
        .map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")
        .map(|value| value.with_timezone(&Utc))
}

fn check_time(value: &Value, field: &str, future_is_error: bool) -> Result<(), &'static str> {
    let parsed = timestamp(value, field)?;
    if (future_is_error && parsed > Utc::now()) || (!future_is_error && parsed <= Utc::now()) {
        return Err("BLOCK_ROOT_EXPIRED");
    }
    Ok(())
}

fn signatures(value: &Value) -> Result<&Vec<Value>, &'static str> {
    let values = value.get("signatures").and_then(Value::as_array).ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    if values.is_empty() || values.len() > MAX_SIGNATURES { return Err("BLOCK_SIGNATURE_THRESHOLD"); }
    Ok(values)
}

fn role<'a>(root: &'a Value, name: &str) -> Result<&'a Value, &'static str> {
    root.get("roles").and_then(Value::as_object).and_then(|roles| roles.get(name))
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
    let allowed: BTreeSet<String> = role_value.get("key_ids").and_then(Value::as_array)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?.iter()
        .map(|item| item.as_str().map(str::to_owned).ok_or("BLOCK_NATIVE_TRUST_VERIFICATION"))
        .collect::<Result<_, _>>()?;
    let threshold = role_value.get("threshold").and_then(Value::as_u64).ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")? as usize;
    if threshold == 0 || threshold > allowed.len() { return Err(error); }
    let schema = string(document, "schema_version")?;
    let payload = canonical_without_signatures(document)?;
    let payload_digest = sha256(&payload);
    let mut message = Vec::with_capacity(DOMAIN.len() + document_type.len() + schema.len() + payload.len() + 2);
    message.extend_from_slice(DOMAIN);
    message.extend_from_slice(document_type.as_bytes());
    message.push(0);
    message.extend_from_slice(schema.as_bytes());
    message.push(0);
    message.extend_from_slice(&payload);
    let mut valid = BTreeSet::new();
    let mut rejected = 0;
    for envelope in signatures(document)? {
        if exact(envelope, &["key_id", "signature"]).is_err() {
            rejected += 1;
            continue;
        }
        let Ok(key_id) = string(envelope, "key_id") else {
            rejected += 1;
            continue;
        };
        if valid.contains(key_id) || !allowed.contains(key_id) || revoked.contains(key_id) {
            rejected += 1;
            continue;
        }
        let Some(key) = keys.get(key_id) else { rejected += 1; continue; };
        exact(key, &["algorithm", "public_key"])?;
        if string(key, "algorithm")? != "ed25519" { rejected += 1; continue; }
        let Ok(public) = URL_SAFE_NO_PAD.decode(string(key, "public_key")?) else {
            rejected += 1;
            continue;
        };
        let Ok(signature_text) = string(envelope, "signature") else {
            rejected += 1;
            continue;
        };
        let Ok(signature) = URL_SAFE_NO_PAD.decode(signature_text) else {
            rejected += 1;
            continue;
        };
        if public.len() != 32 || signature.len() != 64 { rejected += 1; continue; }
        if UnparsedPublicKey::new(&ED25519, public).verify(&message, &signature).is_ok() {
            valid.insert(key_id.to_owned());
        } else {
            rejected += 1;
        }
    }
    if valid.len() < threshold { return Err(error); }
    Ok(VerifiedThreshold { valid_signer_ids: valid.into_iter().collect(), rejected_envelope_count: rejected, payload_digest })
}

fn validate_root(root: &Value, enforce_expiration: bool) -> Result<(), &'static str> {
    exact(root, &["schema_version", "policy_id", "version", "expires_at_utc", "consistent_snapshot", "keys", "roles", "previous_root_digest", "signatures"])?;
    if string(root, "schema_version")? != "butler.firstscreen.root-policy.v1"
        || string(root, "policy_id")? != "butler-firstscreen-trust"
        || root.get("consistent_snapshot") != Some(&Value::Bool(true))
    { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    version(root)?;
    if enforce_expiration {
        check_time(root, "expires_at_utc", false)?;
    } else {
        timestamp(root, "expires_at_utc")?;
    }
    let keys = root.get("keys").and_then(Value::as_object).ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    if keys.is_empty() || keys.len() > MAX_KEYS { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    for (key_id, key) in keys {
        exact(key, &["algorithm", "public_key"])?;
        let public = URL_SAFE_NO_PAD.decode(string(key, "public_key")?).map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?;
        if string(key, "algorithm")? != "ed25519" || public.len() != 32
            || format!("ed25519.{}", sha256(&public)) != *key_id
        { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    }
    let roles = root.get("roles").and_then(Value::as_object).ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let actual_roles: BTreeSet<&str> = roles.keys().map(String::as_str).collect();
    let required_roles: BTreeSet<&str> = ["root", "risk-decision", "revocation", "release"].into_iter().collect();
    if actual_roles != required_roles { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    for name in required_roles { role(root, name)?; }
    match root.get("previous_root_digest") {
        Some(Value::Null) => {}
        Some(Value::String(value)) if is_sha256(value) => {}
        _ => return Err("BLOCK_NATIVE_TRUST_VERIFICATION"),
    }
    Ok(())
}

fn unique_strings(value: &Value, field: &str) -> Result<BTreeSet<String>, &'static str> {
    let values = value
        .get(field)
        .and_then(Value::as_array)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let result: BTreeSet<String> = values
        .iter()
        .map(|item| {
            item.as_str()
                .filter(|item| !item.is_empty())
                .map(str::to_owned)
                .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")
        })
        .collect::<Result<_, _>>()?;
    if result.len() != values.len() {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    Ok(result)
}

fn unique_u64s(value: &Value, field: &str) -> Result<BTreeSet<u64>, &'static str> {
    let values = value
        .get(field)
        .and_then(Value::as_array)
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let result: BTreeSet<u64> = values
        .iter()
        .map(|item| item.as_u64().ok_or("BLOCK_NATIVE_TRUST_VERIFICATION"))
        .collect::<Result<_, _>>()?;
    if result.len() != values.len() {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    Ok(result)
}

fn revoked_keys(revocations: &Value) -> Result<BTreeSet<String>, &'static str> {
    unique_strings(revocations, "revoked_key_ids")
}

fn configured_artifact_paths() -> Result<BTreeMap<String, PathBuf>, &'static str> {
    [
        ("source_archive", "BUTLER_FIRSTSCREEN_SOURCE_ARCHIVE_PATH"),
        ("web_dist_archive", "BUTLER_FIRSTSCREEN_WEB_DIST_ARCHIVE_PATH"),
        ("macos_artifact", "BUTLER_FIRSTSCREEN_MACOS_ARTIFACT_PATH"),
        ("sbom", "BUTLER_FIRSTSCREEN_SBOM_PATH"),
    ]
    .into_iter()
    .map(|(logical_name, variable)| {
        std::env::var_os(variable)
            .filter(|value| !value.is_empty())
            .map(|value| (logical_name.to_owned(), PathBuf::from(value)))
            .ok_or("BLOCK_RELEASE_SUBJECT_MISMATCH")
    })
    .collect()
}

fn open_artifact(path: &Path) -> Result<File, &'static str> {
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW);
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        const FILE_FLAG_OPEN_REPARSE_POINT: u32 = 0x0020_0000;
        options.custom_flags(FILE_FLAG_OPEN_REPARSE_POINT);
    }
    let file = options.open(path).map_err(|_| "BLOCK_RELEASE_SUBJECT_MISMATCH")?;
    let metadata = file
        .metadata()
        .map_err(|_| "BLOCK_RELEASE_SUBJECT_MISMATCH")?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > MAX_ARTIFACT_BYTES {
        return Err("BLOCK_RELEASE_SUBJECT_MISMATCH");
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.nlink() != 1
            || metadata.uid() != unsafe { libc::geteuid() }
            || metadata.mode() & 0o022 != 0
        {
            return Err("BLOCK_RELEASE_SUBJECT_MISMATCH");
        }
    }
    #[cfg(windows)]
    {
        if metadata.file_type().is_symlink() {
            return Err("BLOCK_RELEASE_SUBJECT_MISMATCH");
        }
    }
    Ok(file)
}

fn verify_artifact(
    path: &Path,
    expected_size: u64,
    expected_digest: &str,
) -> Result<File, &'static str> {
    if expected_size == 0 || expected_size > MAX_ARTIFACT_BYTES {
        return Err("BLOCK_RELEASE_SUBJECT_MISMATCH");
    }
    let mut file = open_artifact(path)?;
    let before = file
        .metadata()
        .map_err(|_| "BLOCK_RELEASE_SUBJECT_MISMATCH")?;
    if before.len() != expected_size {
        return Err("BLOCK_RELEASE_SUBJECT_MISMATCH");
    }
    let mut hasher = Sha256::new();
    let mut observed = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|_| "BLOCK_RELEASE_SUBJECT_MISMATCH")?;
        if count == 0 {
            break;
        }
        observed = observed
            .checked_add(count as u64)
            .ok_or("BLOCK_RELEASE_SUBJECT_MISMATCH")?;
        if observed > expected_size {
            return Err("BLOCK_RELEASE_SUBJECT_MISMATCH");
        }
        hasher.update(&buffer[..count]);
    }
    let after = file
        .metadata()
        .map_err(|_| "BLOCK_RELEASE_SUBJECT_MISMATCH")?;
    if observed != expected_size
        || before.len() != after.len()
        || format!("{:x}", hasher.finalize()) != expected_digest
    {
        return Err("BLOCK_RELEASE_SUBJECT_MISMATCH");
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if before.dev() != after.dev()
            || before.ino() != after.ino()
            || before.mtime() != after.mtime()
            || before.mtime_nsec() != after.mtime_nsec()
        {
            return Err("BLOCK_RELEASE_SUBJECT_MISMATCH");
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if before.last_write_time() != after.last_write_time() {
            return Err("BLOCK_RELEASE_SUBJECT_MISMATCH");
        }
    }
    Ok(file)
}

pub fn verify_update(
    request: &VerifyAndCommitRequest,
    current: Option<&TrustedState>,
) -> Result<VerifiedUpdate, &'static str> {
    let artifact_paths = configured_artifact_paths()?;
    verify_update_with_artifacts(request, current, &artifact_paths)
}

pub fn revalidate_persisted_state(state: &TrustedState) -> Result<(), &'static str> {
    super::state::validate_state(state)?;
    let root = parse(&state.current_root_canonical)?;
    validate_root(&root, true)?;
    let keys = root
        .get("keys")
        .and_then(Value::as_object)
        .ok_or("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?;
    let empty = BTreeSet::new();
    let root_threshold = verify_threshold(
        "root-policy",
        &root,
        keys,
        role(&root, "root")?,
        &empty,
        "BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK",
    )?;
    if root_threshold.payload_digest != state.root_digest
        || root_threshold.valid_signer_ids != state.valid_root_signer_ids
    {
        return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
    }

    let revocations = parse(&state.current_revocations_canonical)?;
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
        || string(&revocations, "root_policy_digest")? != state.root_digest
        || version(&revocations)? != state.revocation_version
    {
        return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
    }
    check_time(&revocations, "generated_at_utc", true)?;
    check_time(&revocations, "expires_at_utc", false)?;
    if timestamp(&revocations, "generated_at_utc")?
        >= timestamp(&revocations, "expires_at_utc")?
    {
        return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
    }
    unique_strings(&revocations, "revoked_decision_ids")?;
    let revoked = unique_strings(&revocations, "revoked_key_ids")?;
    unique_u64s(&revocations, "revoked_epochs")?;
    let revocation_threshold = verify_threshold(
        "revocations",
        &revocations,
        keys,
        role(&root, "revocation")?,
        &empty,
        "BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK",
    )?;
    if revocation_threshold.payload_digest != state.revocation_digest
        || revocation_threshold.valid_signer_ids != state.valid_revocation_signer_ids
        || root_threshold
            .valid_signer_ids
            .iter()
            .chain(revocation_threshold.valid_signer_ids.iter())
            .any(|key_id| revoked.contains(key_id))
    {
        return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
    }

    let embedded_build = option_env!("BUTLER_BUILD_CONTEXT_DIGEST")
        .ok_or("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?;
    let embedded_commit = option_env!("BUTLER_SOURCE_COMMIT_OID")
        .ok_or("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?;
    let embedded_tree = option_env!("BUTLER_SOURCE_TREE_OID")
        .ok_or("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?;
    if embedded_build != state.native_build_identity_digest
        || embedded_commit != state.source_commit_oid
        || embedded_tree != state.source_tree_oid
    {
        return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
    }
    Ok(())
}

fn verify_update_with_artifacts(
    request: &VerifyAndCommitRequest,
    current: Option<&TrustedState>,
    artifact_paths: &BTreeMap<String, PathBuf>,
) -> Result<VerifiedUpdate, &'static str> {
    if request.schema_version != COMMAND_SCHEMA
        || !matches!(request.environment.as_str(), "development" | "release")
        || !is_oid(&request.source_commit_oid)
        || !is_oid(&request.source_tree_oid)
        || !is_sha256(&request.native_build_identity_digest)
        || request.request_id.is_empty()
    { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    let embedded_build_digest = option_env!("BUTLER_BUILD_CONTEXT_DIGEST")
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let embedded_commit = option_env!("BUTLER_SOURCE_COMMIT_OID")
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let embedded_tree = option_env!("BUTLER_SOURCE_TREE_OID")
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    if embedded_build_digest != request.native_build_identity_digest
        || embedded_commit != request.source_commit_oid
        || embedded_tree != request.source_tree_oid
    { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    let root = parse(&request.root_json)?;
    validate_root(&root, true)?;
    let root_keys = root.get("keys").and_then(Value::as_object).ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let empty = BTreeSet::new();
    let new_threshold = verify_threshold("root-policy", &root, root_keys, role(&root, "root")?, &empty, "BLOCK_ROOT_NEW_THRESHOLD")?;
    debug_assert!(new_threshold.rejected_envelope_count <= MAX_SIGNATURES);
    let root_digest = new_threshold.payload_digest.clone();
    let root_version = version(&root)?;
    let (old_root_digest, valid_old_root_signer_ids) = match current {
        None => {
            if request.expected_generation != 0 || root_version != 1 || !root.get("previous_root_digest").is_some_and(Value::is_null) {
                return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
            }
            let anchor = option_env!("BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256")
                .ok_or("BLOCK_ROOT_BOOTSTRAP_ANCHOR")?;
            if !is_sha256(anchor) || anchor != root_digest { return Err("BLOCK_ROOT_BOOTSTRAP_ANCHOR"); }
            (None, Vec::new())
        }
        Some(state) => {
            if request.expected_generation != state.generation { return Err("BLOCK_TRUST_STATE_CAS"); }
            let old_root = parse(&state.current_root_canonical)?;
            // TUF 1.0 root transition semantics deliberately ignore expiry of the
            // already-trusted root while authenticating exactly N+1. The final
            // candidate root above must still be current.
            validate_root(&old_root, false)?;
            if root_version == state.root_version {
                if root_digest != state.root_digest { return Err("BLOCK_ROOT_VERSION_SEQUENCE"); }
                (Some(state.root_digest.clone()), state.valid_root_signer_ids.clone())
            } else {
                if root_version != state.root_version + 1 { return Err("BLOCK_ROOT_VERSION_SEQUENCE"); }
                if root.get("previous_root_digest").and_then(Value::as_str) != Some(state.root_digest.as_str()) {
                    return Err("BLOCK_ROOT_PREVIOUS_DIGEST");
                }
                let old_keys = old_root.get("keys").and_then(Value::as_object).ok_or("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?;
                let old = verify_threshold("root-policy", &root, old_keys, role(&old_root, "root")?, &empty, "BLOCK_ROOT_OLD_THRESHOLD")?;
                (Some(state.root_digest.clone()), old.valid_signer_ids)
            }
        }
    };

    let revocations = parse(&request.revocations_json)?;
    exact(&revocations, &["schema_version", "policy_id", "version", "generated_at_utc", "expires_at_utc", "previous_digest", "root_policy_digest", "revoked_decision_ids", "revoked_key_ids", "revoked_epochs", "signatures"])?;
    if string(&revocations, "schema_version")? != "butler.firstscreen.revocations.v2"
        || string(&revocations, "policy_id")? != "butler-firstscreen-trust"
        || string(&revocations, "root_policy_digest")? != root_digest
    { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    check_time(&revocations, "generated_at_utc", true)?;
    check_time(&revocations, "expires_at_utc", false)?;
    if timestamp(&revocations, "generated_at_utc")?
        >= timestamp(&revocations, "expires_at_utc")?
    {
        return Err("BLOCK_REVOCATION_EXPIRED");
    }
    unique_strings(&revocations, "revoked_decision_ids")?;
    unique_strings(&revocations, "revoked_key_ids")?;
    unique_u64s(&revocations, "revoked_epochs")?;
    let revocation_version = version(&revocations)?;
    if let Some(state) = current {
        if revocation_version < state.revocation_version
            || (revocation_version == state.revocation_version
                && sha256(&canonical_without_signatures(&revocations)?) != state.revocation_digest)
            || (revocation_version > state.revocation_version
                && (revocation_version != state.revocation_version + 1
                    || revocations.get("previous_digest").and_then(Value::as_str) != Some(state.revocation_digest.as_str())))
        { return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK"); }
    } else if revocation_version != 1 || !revocations.get("previous_digest").is_some_and(Value::is_null) {
        return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK");
    }
    let revocation_threshold = verify_threshold("revocations", &revocations, root_keys, role(&root, "revocation")?, &empty, "BLOCK_REVOCATION_THRESHOLD")?;
    debug_assert!(revocation_threshold.rejected_envelope_count <= MAX_SIGNATURES);
    if let Some(state) = current {
        for field in ["revoked_decision_ids", "revoked_key_ids", "revoked_epochs"] {
            let previous: BTreeSet<String> = parse(&state.current_revocations_canonical)?
                .get(field).and_then(Value::as_array).ok_or("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?
                .iter().map(|item| item.to_string()).collect();
            let candidate: BTreeSet<String> = revocations.get(field).and_then(Value::as_array)
                .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?.iter().map(|item| item.to_string()).collect();
            if !previous.is_subset(&candidate) { return Err("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK"); }
        }
    }
    let revoked = revoked_keys(&revocations)?;
    if new_threshold
        .valid_signer_ids
        .iter()
        .chain(revocation_threshold.valid_signer_ids.iter())
        .any(|key_id| revoked.contains(key_id))
    {
        return Err("BLOCK_REVOCATION_THRESHOLD");
    }

    let decision = parse(&request.decision_json)?;
    exact(&decision, &["schema_version", "policy_id", "decision_id", "version", "approved_at_utc", "expires_at_utc", "scope", "protection_boundary", "data_classification", "owner_role", "revocation_epoch", "root_policy_digest", "source_blob_digest", "canonical_ssot_location", "signatures"])?;
    if string(&decision, "schema_version")? != "butler.firstscreen.risk-decision.v2"
        || string(&decision, "policy_id")? != "butler-firstscreen-trust"
        || string(&decision, "root_policy_digest")? != root_digest
    { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    let decision_id = string(&decision, "decision_id")?;
    if decision_id.is_empty()
        || decision_id.len() > 128
        || decision.get("version").and_then(Value::as_u64).is_none_or(|value| value == 0)
        || !is_sha256(string(&decision, "source_blob_digest")?)
    {
        return Err("BLOCK_DECISION_SCHEMA");
    }
    let scope = unique_strings(&decision, "scope")?;
    if scope
        != ["CONVERSATION_TITLE", "FTS_TITLE_INDEX"]
            .into_iter()
            .map(str::to_owned)
            .collect()
    {
        return Err("BLOCK_DECISION_SCOPE");
    }
    let boundaries = unique_strings(&decision, "protection_boundary")?;
    if ![
        "ON_DEVICE",
        "OS_USER_BOUNDARY",
        "APP_DATA_PATH",
        "OWNER_MODE_GUARD",
    ]
    .into_iter()
    .all(|boundary| boundaries.contains(boundary))
        || string(&decision, "data_classification")? != "CONFIDENTIAL"
        || string(&decision, "owner_role")? != "ATLINK_REPRESENTATIVE"
        || decision.get("revocation_epoch").and_then(Value::as_u64).is_none()
    {
        return Err("BLOCK_DECISION_SCOPE");
    }
    let location = string(&decision, "canonical_ssot_location")?;
    if location.is_empty()
        || location.len() > 512
        || location.starts_with('/')
        || location.ends_with('/')
        || location.contains('\\')
        || location
            .split('/')
            .any(|segment| segment.is_empty() || matches!(segment, "." | ".."))
    {
        return Err("BLOCK_DECISION_SCHEMA");
    }
    check_time(&decision, "approved_at_utc", true)?;
    check_time(&decision, "expires_at_utc", false)?;
    if timestamp(&decision, "approved_at_utc")?
        >= timestamp(&decision, "expires_at_utc")?
    {
        return Err("BLOCK_DECISION_EXPIRED");
    }
    let decision_threshold = verify_threshold(
        "risk-decision",
        &decision,
        root_keys,
        role(&root, "risk-decision")?,
        &revoked,
        "BLOCK_DECISION_THRESHOLD",
    )?;
    let revoked_decisions = unique_strings(&revocations, "revoked_decision_ids")?;
    let revoked_epochs = unique_u64s(&revocations, "revoked_epochs")?;
    if revoked_decisions.contains(decision_id)
        || decision
            .get("revocation_epoch")
            .and_then(Value::as_u64)
            .is_some_and(|epoch| revoked_epochs.contains(&epoch))
        || decision_threshold
            .valid_signer_ids
            .iter()
            .any(|key_id| revoked.contains(key_id))
    {
        return Err("BLOCK_DECISION_REVOKED");
    }

    let release = parse(&request.release_subjects_json)?;
    exact(&release, &["schema_version", "policy_id", "build_context_digest", "subjects", "created_at_utc", "signatures"])?;
    if string(&release, "schema_version")? != "butler.firstscreen.release-subjects.v1"
        || string(&release, "policy_id")? != "butler-firstscreen-trust"
        || string(&release, "build_context_digest")? != request.native_build_identity_digest
    { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
    let subjects = release.get("subjects").and_then(Value::as_object).ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?;
    let subject_names: BTreeSet<&str> = subjects.keys().map(String::as_str).collect();
    if subject_names != ["source_archive", "web_dist_archive", "macos_artifact", "sbom"].into_iter().collect() {
        return Err("BLOCK_NATIVE_TRUST_VERIFICATION");
    }
    let mut artifact_handles = Vec::with_capacity(subjects.len());
    for (logical_name, subject) in subjects {
        exact(subject, &["name", "size", "sha256", "build_context_digest"])?;
        let expected_size = subject.get("size").and_then(Value::as_u64)
            .ok_or("BLOCK_RELEASE_SUBJECT_MISMATCH")?;
        let expected_digest = string(subject, "sha256")?;
        if string(subject, "name")?.is_empty()
            || string(subject, "name")?.len() > 200
            || !is_sha256(expected_digest)
            || string(subject, "build_context_digest")? != request.native_build_identity_digest
            || expected_size == 0
            || expected_size > MAX_ARTIFACT_BYTES
        { return Err("BLOCK_NATIVE_TRUST_VERIFICATION"); }
        let path = artifact_paths
            .get(logical_name)
            .ok_or("BLOCK_RELEASE_SUBJECT_MISMATCH")?;
        artifact_handles.push(verify_artifact(path, expected_size, expected_digest)?);
    }
    check_time(&release, "created_at_utc", true)?;
    let release_threshold = verify_threshold(
        "release-subjects",
        &release,
        root_keys,
        role(&root, "release")?,
        &revoked,
        "BLOCK_RELEASE_THRESHOLD",
    )?;
    // Keep the verified descriptors alive until every signed subject and the
    // complete update have been accepted. Activation is intentionally false;
    // any future consumer must reopen and reverify through this same routine.
    debug_assert_eq!(artifact_handles.len(), 4);
    let rejected_envelope_count = new_threshold.rejected_envelope_count
        + revocation_threshold.rejected_envelope_count
        + decision_threshold.rejected_envelope_count
        + release_threshold.rejected_envelope_count;
    let rejected_envelope_reasons = if rejected_envelope_count == 0 {
        Vec::new()
    } else {
        vec!["INVALID_OR_UNTRUSTED_SIGNATURE_ENVELOPE".to_owned()]
    };

    Ok(VerifiedUpdate {
        root_canonical: String::from_utf8(canonical(&root)?).map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?,
        root_digest,
        root_version,
        old_root_digest,
        valid_old_root_signer_ids,
        valid_new_root_signer_ids: new_threshold.valid_signer_ids,
        revocations_canonical: String::from_utf8(canonical(&revocations)?).map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?,
        revocation_digest: revocation_threshold.payload_digest,
        revocation_version,
        valid_revocation_signer_ids: revocation_threshold.valid_signer_ids,
        rejected_envelope_count,
        rejected_envelope_reasons,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use ring::signature::{Ed25519KeyPair, KeyPair};
    use serde_json::json;
    use std::io::{Read as _, Seek, SeekFrom};
    use std::time::{SystemTime, UNIX_EPOCH};

    fn signed_threshold_document(
        extra_envelopes: Vec<Value>,
    ) -> (Value, Map<String, Value>, Value) {
        let pair = Ed25519KeyPair::from_seed_unchecked(&[7_u8; 32]).unwrap();
        let public = pair.public_key().as_ref();
        let key_id = format!("ed25519.{}", sha256(public));
        let mut document = json!({
            "schema_version": "test.v1",
            "payload": "authoritative",
            "signatures": []
        });
        let payload = canonical_without_signatures(&document).unwrap();
        let mut message = Vec::new();
        message.extend_from_slice(DOMAIN);
        message.extend_from_slice(b"test-document");
        message.push(0);
        message.extend_from_slice(b"test.v1");
        message.push(0);
        message.extend_from_slice(&payload);
        let valid = json!({
            "key_id": key_id,
            "signature": URL_SAFE_NO_PAD.encode(pair.sign(&message).as_ref())
        });
        let mut envelopes = extra_envelopes;
        envelopes.push(valid);
        document["signatures"] = Value::Array(envelopes);
        let mut keys = Map::new();
        keys.insert(
            key_id.clone(),
            json!({
                "algorithm": "ed25519",
                "public_key": URL_SAFE_NO_PAD.encode(public)
            }),
        );
        let role = json!({"key_ids": [key_id], "threshold": 1});
        (document, keys, role)
    }

    #[test]
    fn rs_env_001_malformed_envelope_cannot_poison_valid_quorum() {
        let (document, keys, role) =
            signed_threshold_document(vec![json!({"key_id": "malformed"})]);
        let verified = verify_threshold(
            "test-document",
            &document,
            &keys,
            &role,
            &BTreeSet::new(),
            "BLOCK_SIGNATURE_THRESHOLD",
        )
        .unwrap();
        assert_eq!(verified.valid_signer_ids.len(), 1);
        assert_eq!(verified.rejected_envelope_count, 1);
    }

    #[test]
    fn rs_env_002_invalid_base64_cannot_poison_valid_quorum() {
        let (mut document, keys, role) = signed_threshold_document(Vec::new());
        let key_id = role["key_ids"][0].as_str().unwrap();
        document["signatures"]
            .as_array_mut()
            .unwrap()
            .insert(0, json!({"key_id": key_id, "signature": "*"}));
        let verified = verify_threshold(
            "test-document",
            &document,
            &keys,
            &role,
            &BTreeSet::new(),
            "BLOCK_SIGNATURE_THRESHOLD",
        )
        .unwrap();
        assert_eq!(verified.valid_signer_ids.len(), 1);
        assert_eq!(verified.rejected_envelope_count, 1);
    }

    #[test]
    fn rs_rot_001_expired_trusted_root_authenticates_only_transition() {
        let pair = Ed25519KeyPair::from_seed_unchecked(&[9_u8; 32]).unwrap();
        let public = pair.public_key().as_ref();
        let key_id = format!("ed25519.{}", sha256(public));
        let role = json!({"key_ids": [key_id.clone()], "threshold": 1});
        let mut keys = Map::new();
        keys.insert(
            key_id.clone(),
            json!({
                "algorithm": "ed25519",
                "public_key": URL_SAFE_NO_PAD.encode(public)
            }),
        );
        let root = json!({
            "schema_version": "butler.firstscreen.root-policy.v1",
            "policy_id": "butler-firstscreen-trust",
            "version": 1,
            "expires_at_utc": "2000-01-01T00:00:00Z",
            "consistent_snapshot": true,
            "keys": keys,
            "roles": {
                "root": role.clone(),
                "risk-decision": role.clone(),
                "revocation": role.clone(),
                "release": role
            },
            "previous_root_digest": null,
            "signatures": [{"key_id": "ignored", "signature": "ignored"}]
        });
        assert!(validate_root(&root, false).is_ok());
        assert_eq!(validate_root(&root, true), Err("BLOCK_ROOT_EXPIRED"));
    }

    #[test]
    fn rs_rel_001_path_replacement_does_not_change_verified_open_handle() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let directory = std::env::temp_dir().join(format!(
            "butler-runtime-trust-{}-{unique}",
            std::process::id()
        ));
        std::fs::create_dir(&directory).unwrap();
        let path = directory.join("artifact.bin");
        let moved = directory.join("verified.bin");
        let original = b"verified artifact bytes";
        std::fs::write(&path, original).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        }
        let mut handle = verify_artifact(&path, original.len() as u64, &sha256(original)).unwrap();
        std::fs::rename(&path, &moved).unwrap();
        std::fs::write(&path, b"attacker replacement").unwrap();
        handle.seek(SeekFrom::Start(0)).unwrap();
        let mut observed = Vec::new();
        handle.read_to_end(&mut observed).unwrap();
        assert_eq!(observed, original);
        drop(handle);
        std::fs::remove_dir_all(directory).unwrap();
    }
}
