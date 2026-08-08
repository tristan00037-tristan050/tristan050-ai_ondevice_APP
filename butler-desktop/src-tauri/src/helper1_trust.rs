use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fs;
use tauri::Manager;

#[derive(Serialize)]
pub struct Helper1ExecutionTrustAnchor {
    schema_version: &'static str,
    public_key_b64: String,
    public_key_sha256: String,
    session_digest: String,
    subject_commit: String,
    subject_tree: String,
}

fn is_object_id(value: &str) -> bool {
    matches!(value.len(), 40 | 64)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

#[tauri::command]
pub fn get_helper1_execution_trust_anchor(
    app: tauri::AppHandle,
) -> Result<Helper1ExecutionTrustAnchor, String> {
    if option_env!("BUTLER_RELEASE_DISTRIBUTION") != Some("1") {
        return Err("HELPER1_TRUST_ANCHOR_UNAVAILABLE".to_string());
    }
    let public_key_b64 = option_env!("BUTLER_HELPER1_EXECUTION_PUBLIC_KEY_B64")
        .ok_or_else(|| "HELPER1_TRUST_ANCHOR_UNAVAILABLE".to_string())?;
    let expected_digest = option_env!("BUTLER_HELPER1_EXECUTION_PUBLIC_KEY_SHA256")
        .ok_or_else(|| "HELPER1_TRUST_ANCHOR_UNAVAILABLE".to_string())?;
    let subject_commit = option_env!("BUTLER_SOURCE_COMMIT_OID")
        .ok_or_else(|| "HELPER1_TRUST_ANCHOR_UNAVAILABLE".to_string())?;
    let subject_tree = option_env!("BUTLER_SOURCE_TREE_OID")
        .ok_or_else(|| "HELPER1_TRUST_ANCHOR_UNAVAILABLE".to_string())?;
    if !is_object_id(subject_commit) || !is_object_id(subject_tree) {
        return Err("HELPER1_TRUST_SUBJECT_INVALID".to_string());
    }
    let public_key = STANDARD
        .decode(public_key_b64)
        .map_err(|_| "HELPER1_TRUST_ANCHOR_INVALID".to_string())?;
    if public_key.len() != 32 {
        return Err("HELPER1_TRUST_ANCHOR_INVALID".to_string());
    }
    let observed_digest = format!("{:x}", Sha256::digest(&public_key));
    if observed_digest != expected_digest {
        return Err("HELPER1_TRUST_ANCHOR_INVALID".to_string());
    }
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|_| "APP_DATA_DIR_UNAVAILABLE".to_string())?;
    let token_path = app_data_dir.join("ipc").join("sidecar.capability");
    let token_text = fs::read_to_string(&token_path)
        .map_err(|_| "HELPER1_CAPABILITY_SESSION_UNAVAILABLE".to_string())?;
    let token = token_text.trim().as_bytes();
    if token.is_empty() || token.len() > 4096 {
        return Err("HELPER1_CAPABILITY_SESSION_INVALID".to_string());
    }
    Ok(Helper1ExecutionTrustAnchor {
        schema_version: "butler.helper1.execution-trust-anchor.v1",
        public_key_b64: public_key_b64.to_string(),
        public_key_sha256: observed_digest,
        session_digest: format!("{:x}", Sha256::digest(token)),
        subject_commit: subject_commit.to_string(),
        subject_tree: subject_tree.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn object_id_requires_lowercase_hex_and_fixed_length() {
        assert!(is_object_id(&"a".repeat(40)));
        assert!(is_object_id(&"b".repeat(64)));
        assert!(!is_object_id(&"A".repeat(40)));
        assert!(!is_object_id("main"));
    }
}
