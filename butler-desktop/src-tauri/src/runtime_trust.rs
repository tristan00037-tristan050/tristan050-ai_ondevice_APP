//! Native FirstScreen trust authority.
//!
//! Renderer-created receipts are deliberately unsupported.  The only public
//! mutation command accepts raw signed documents and an expected generation;
//! verification, Keychain CAS, receipt construction and read-back all remain
//! inside this native boundary.

mod commands;
mod keychain;
mod state;
mod verifier;

use serde_json::Value;

use state::VerifyAndCommitRequest;

pub use commands::{initialize_authority, AuthorityState};

#[tauri::command]
pub fn verify_and_commit_trust_update(
    request: VerifyAndCommitRequest,
    authority: tauri::State<'_, AuthorityState>,
) -> Result<Value, String> {
    commands::verify_and_commit_trust_update(request, authority)
}
