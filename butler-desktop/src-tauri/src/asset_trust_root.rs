use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

use crate::asset_trust_root_constants::{
    ASSET_REVOKED_KEY_IDS_JSON, ASSET_ROOT_POLICY_SHA256, ASSET_TRUST_EPOCH, ASSET_TRUST_KEYS_JSON,
};

pub const TRUST_ROOT_NOT_CONFIGURED: &str = "TRUST_ROOT_NOT_CONFIGURED";
pub const TRUST_ROOT_CONFIGURED: &str = "TRUST_ROOT_CONFIGURED";

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum TrustRootState {
    Unconfigured,
    Configured,
}

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum SignatureState {
    Missing,
    Invalid,
    Verified,
    Revoked,
    Expired,
}

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ProvenanceState {
    Unverified,
    Verified,
    Rejected,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct AssetSecurityState {
    pub byte_safety_verified: bool,
    pub origin_verified: bool,
    pub trust_root_state: TrustRootState,
    pub signature_state: SignatureState,
    pub provenance_state: ProvenanceState,
    pub release_ready: bool,
    pub external_handoff_allowed: u8,
    pub auto_update_allowed: u8,
    pub operation_scope: &'static str,
}

impl AssetSecurityState {
    pub fn from_root(root: &AssetTrustRoot, byte_safety_verified: bool) -> Self {
        let configured = root.status == TRUST_ROOT_CONFIGURED;
        Self {
            byte_safety_verified,
            origin_verified: false,
            trust_root_state: if configured {
                TrustRootState::Configured
            } else {
                TrustRootState::Unconfigured
            },
            signature_state: SignatureState::Missing,
            provenance_state: ProvenanceState::Unverified,
            release_ready: false,
            external_handoff_allowed: 0,
            auto_update_allowed: 0,
            operation_scope: "INTERNAL_OWNER_ONLY",
        }
    }

    pub fn require_distribution(&self) -> Result<(), &'static str> {
        if self.release_ready && self.origin_verified {
            Ok(())
        } else {
            Err("BLOCK_DISTRIBUTION_WITHOUT_TRUST_ROOT")
        }
    }

    pub fn require_external_handoff(&self) -> Result<(), &'static str> {
        if self.external_handoff_allowed == 1 {
            Ok(())
        } else {
            Err("BLOCK_EXTERNAL_HANDOFF_UNVERIFIED")
        }
    }

    pub fn require_auto_update(&self) -> Result<(), &'static str> {
        if self.auto_update_allowed == 1 {
            Ok(())
        } else {
            Err("BLOCK_AUTO_UPDATE_UNVERIFIED")
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TrustRootKey {
    pub key_id: String,
    pub epoch: u64,
    pub public_key_b64: String,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct AssetTrustRoot {
    pub status: &'static str,
    pub policy_sha256: Option<String>,
    pub current_epoch: Option<u64>,
    pub keys: Vec<TrustRootKey>,
    pub revoked_key_ids: BTreeSet<String>,
}

fn lower_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

pub fn embedded_asset_trust_root() -> Result<AssetTrustRoot, &'static str> {
    let policy = ASSET_ROOT_POLICY_SHA256;
    let keys_json = ASSET_TRUST_KEYS_JSON;
    let revoked_json = ASSET_REVOKED_KEY_IDS_JSON;
    let epoch = ASSET_TRUST_EPOCH;
    if policy.is_empty() && keys_json == "[]" && revoked_json == "[]" && epoch == 0 {
        return Ok(AssetTrustRoot {
            status: TRUST_ROOT_NOT_CONFIGURED,
            policy_sha256: None,
            current_epoch: None,
            keys: Vec::new(),
            revoked_key_ids: BTreeSet::new(),
        });
    }
    if !lower_sha256(policy) {
        return Err("BLOCK_ROOT_POLICY_UNPINNED");
    }
    if epoch == 0 {
        return Err("BLOCK_ROOT_POLICY_UNPINNED");
    }
    let keys: Vec<TrustRootKey> =
        serde_json::from_str(keys_json).map_err(|_| "BLOCK_ROOT_POLICY_UNPINNED")?;
    if keys.is_empty() {
        return Err("BLOCK_ROOT_POLICY_UNPINNED");
    }
    let mut key_ids = BTreeSet::new();
    for key in &keys {
        if key.key_id.is_empty()
            || key.epoch == 0
            || key.epoch > epoch
            || !key_ids.insert(key.key_id.clone())
            || STANDARD
                .decode(&key.public_key_b64)
                .ok()
                .filter(|raw| raw.len() == 32)
                .is_none()
        {
            return Err("BLOCK_ROOT_POLICY_UNPINNED");
        }
    }
    let revoked: BTreeSet<String> =
        serde_json::from_str(revoked_json).map_err(|_| "BLOCK_ROOT_POLICY_UNPINNED")?;
    if revoked.iter().any(|key_id| !key_ids.contains(key_id)) {
        return Err("BLOCK_ROOT_POLICY_UNPINNED");
    }
    if keys
        .iter()
        .filter(|key| key.epoch <= epoch && !revoked.contains(&key.key_id))
        .count()
        == 0
    {
        return Err("BLOCK_TRUST_UNAVAILABLE");
    }
    Ok(AssetTrustRoot {
        status: TRUST_ROOT_CONFIGURED,
        policy_sha256: Some(policy.to_string()),
        current_epoch: Some(epoch),
        keys,
        revoked_key_ids: revoked,
    })
}

pub fn current_asset_security_state(
    byte_safety_verified: bool,
) -> Result<AssetSecurityState, &'static str> {
    let root = embedded_asset_trust_root()?;
    Ok(AssetSecurityState::from_root(&root, byte_safety_verified))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unconfigured_root_is_explicitly_unverified() {
        let root = embedded_asset_trust_root().expect("empty development root is represented");
        if ASSET_ROOT_POLICY_SHA256.is_empty() {
            assert_eq!(root.status, TRUST_ROOT_NOT_CONFIGURED);
            assert!(root.policy_sha256.is_none());
            assert!(root.keys.is_empty());
            let state = AssetSecurityState::from_root(&root, true);
            assert!(state.byte_safety_verified);
            assert!(!state.origin_verified);
            assert_eq!(
                state.require_distribution(),
                Err("BLOCK_DISTRIBUTION_WITHOUT_TRUST_ROOT")
            );
            assert_eq!(
                state.require_external_handoff(),
                Err("BLOCK_EXTERNAL_HANDOFF_UNVERIFIED")
            );
            assert_eq!(
                state.require_auto_update(),
                Err("BLOCK_AUTO_UPDATE_UNVERIFIED")
            );
        }
    }

    #[test]
    fn current_unconfigured_state_matches_the_distribution_deny_contract() {
        if ASSET_ROOT_POLICY_SHA256.is_empty() {
            let state =
                current_asset_security_state(true).expect("development state is representable");
            assert!(state.byte_safety_verified);
            assert!(!state.origin_verified);
            assert_eq!(state.trust_root_state, TrustRootState::Unconfigured);
            assert_eq!(state.signature_state, SignatureState::Missing);
            assert_eq!(state.provenance_state, ProvenanceState::Unverified);
            assert!(!state.release_ready);
            assert_eq!(state.external_handoff_allowed, 0);
            assert_eq!(state.auto_update_allowed, 0);
            assert_eq!(state.operation_scope, "INTERNAL_OWNER_ONLY");
        }
    }
}
