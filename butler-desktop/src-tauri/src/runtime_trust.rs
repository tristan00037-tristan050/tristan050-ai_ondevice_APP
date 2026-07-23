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

pub use commands::{initialize_authority, verify_and_commit_trust_update, AuthorityState};
