use std::sync::Mutex;

use chrono::Utc;
use serde_json::Value;

use super::keychain;
use super::state::{
    canonical, sha256, validate_state, NativeTrustReceipt, TrustedState, VerifyAndCommitRequest,
    RECEIPT_SCHEMA, STATE_SCHEMA,
};
use super::verifier::verify_update;

pub struct AuthorityState(pub Mutex<Option<TrustedState>>);

pub fn initialize_authority() -> Result<AuthorityState, &'static str> {
    let state = match keychain::read()? {
        None => None,
        Some(raw) => {
            let state: TrustedState = serde_json::from_slice(&raw)
                .map_err(|_| "BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")?;
            validate_state(&state)?;
            Some(state)
        }
    };
    Ok(AuthorityState(Mutex::new(state)))
}

fn receipt_digest(receipt: &NativeTrustReceipt) -> Result<String, &'static str> {
    let mut value = serde_json::to_value(receipt).map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION")?;
    value
        .as_object_mut()
        .ok_or("BLOCK_NATIVE_TRUST_VERIFICATION")?
        .remove("receipt_digest");
    Ok(sha256(&canonical(&value)?))
}

pub fn verify_and_commit_trust_update(
    request: VerifyAndCommitRequest,
    authority: tauri::State<'_, AuthorityState>,
) -> Result<Value, String> {
    let mut guard = authority
        .0
        .lock()
        .map_err(|_| "BLOCK_TRUST_STATE_CAS".to_owned())?;
    let persisted_raw = keychain::read().map_err(str::to_owned)?;
    let persisted = persisted_raw
        .as_deref()
        .map(serde_json::from_slice::<TrustedState>)
        .transpose()
        .map_err(|_| "BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK".to_owned())?;
    if let Some(state) = persisted.as_ref() {
        validate_state(state).map_err(str::to_owned)?;
    }
    let in_memory_digest = guard
        .as_ref()
        .map(|state| canonical(state).map(|raw| sha256(&raw)))
        .transpose()
        .map_err(str::to_owned)?;
    let persisted_digest = persisted
        .as_ref()
        .map(|state| canonical(state).map(|raw| sha256(&raw)))
        .transpose()
        .map_err(str::to_owned)?;
    if in_memory_digest != persisted_digest {
        return Err("BLOCK_TRUST_STATE_CAS".into());
    }

    let verified = verify_update(&request, persisted.as_ref()).map_err(str::to_owned)?;
    let generation_before = persisted.as_ref().map_or(0, |state| state.generation);
    let generation_after = generation_before
        .checked_add(1)
        .ok_or("BLOCK_TRUST_STATE_CAS")?;
    let issued_at = Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
    let previous_receipt = persisted
        .as_ref()
        .and_then(|state| state.previous_trusted_state_receipt_digest.clone());
    let mut candidate = TrustedState {
        schema_version: STATE_SCHEMA.into(),
        policy_id: "butler-firstscreen-trust".into(),
        environment: request.environment.clone(),
        generation: generation_after,
        current_root_canonical: verified.root_canonical,
        root_digest: verified.root_digest.clone(),
        root_version: verified.root_version,
        current_revocations_canonical: verified.revocations_canonical,
        revocation_digest: verified.revocation_digest.clone(),
        revocation_version: verified.revocation_version,
        valid_root_signer_ids: verified.valid_new_root_signer_ids.clone(),
        valid_revocation_signer_ids: verified.valid_revocation_signer_ids.clone(),
        source_commit_oid: request.source_commit_oid.clone(),
        source_tree_oid: request.source_tree_oid.clone(),
        native_build_identity_digest: request.native_build_identity_digest.clone(),
        previous_trusted_state_receipt_digest: previous_receipt.clone(),
        committed_at_utc: issued_at.clone(),
        runtime_activation_allowed: false,
    };
    let committed_state_digest = sha256(&canonical(&candidate).map_err(str::to_owned)?);
    let mut receipt = NativeTrustReceipt {
        schema_version: RECEIPT_SCHEMA,
        request_id: request.request_id,
        status: "VERIFIED_AND_COMMITTED",
        error_code: "OK",
        generation_before,
        generation_after,
        old_root_digest: verified.old_root_digest,
        new_root_digest: verified.root_digest,
        root_version: verified.root_version,
        revocation_digest: verified.revocation_digest,
        revocation_version: verified.revocation_version,
        valid_old_root_signer_ids: verified.valid_old_root_signer_ids,
        valid_new_root_signer_ids: verified.valid_new_root_signer_ids,
        valid_revocation_signer_ids: verified.valid_revocation_signer_ids,
        source_commit_oid: request.source_commit_oid,
        source_tree_oid: request.source_tree_oid,
        native_build_identity_digest: request.native_build_identity_digest,
        committed_state_digest,
        previous_receipt_digest: previous_receipt,
        issued_at_utc: issued_at,
        runtime_activation_allowed: false,
        receipt_digest: String::new(),
    };
    receipt.receipt_digest = receipt_digest(&receipt).map_err(str::to_owned)?;
    candidate.previous_trusted_state_receipt_digest = Some(receipt.receipt_digest.clone());
    let encoded = canonical(&candidate).map_err(str::to_owned)?;
    keychain::write(&encoded, persisted.is_some()).map_err(str::to_owned)?;
    let read_back = keychain::read()
        .map_err(str::to_owned)?
        .ok_or("BLOCK_TRUST_STATE_CAS")?;
    if read_back != encoded {
        return Err("BLOCK_TRUST_STATE_CAS".into());
    }
    let confirmed: TrustedState =
        serde_json::from_slice(&read_back).map_err(|_| "BLOCK_TRUST_STATE_CAS")?;
    validate_state(&confirmed).map_err(str::to_owned)?;
    *guard = Some(confirmed);
    serde_json::to_value(receipt).map_err(|_| "BLOCK_NATIVE_TRUST_VERIFICATION".into())
}
