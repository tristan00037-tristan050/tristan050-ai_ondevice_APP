use sha2::{Digest, Sha256};
use std::process::Command;

fn git_identity(argument: &str) -> Option<String> {
    let output = Command::new("git").args(["rev-parse", argument]).output().ok()?;
    if !output.status.success() {
        return None;
    }
    String::from_utf8(output.stdout).ok().map(|value| value.trim().to_owned())
}

fn main() {
    println!("cargo:rerun-if-env-changed=BUTLER_BUILD_CONTEXT_DIGEST");
    println!("cargo:rerun-if-env-changed=BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256");
    println!("cargo:rerun-if-env-changed=BUTLER_SOURCE_COMMIT_OID");
    println!("cargo:rerun-if-env-changed=BUTLER_SOURCE_TREE_OID");
    let release = std::env::var("PROFILE").as_deref() == Ok("release");
    let source_commit = std::env::var("BUTLER_SOURCE_COMMIT_OID")
        .ok()
        .or_else(|| (!release).then(|| git_identity("HEAD")).flatten());
    let source_tree = std::env::var("BUTLER_SOURCE_TREE_OID")
        .ok()
        .or_else(|| (!release).then(|| git_identity("HEAD^{tree}")).flatten());
    let digest = std::env::var("BUTLER_BUILD_CONTEXT_DIGEST").unwrap_or_else(|_| {
        if release {
            panic!("BUILD_CONTEXT_DIGEST_REQUIRED");
        }
        let commit = source_commit.as_deref().expect("SOURCE_COMMIT_OID_REQUIRED");
        let tree = source_tree.as_deref().expect("SOURCE_TREE_OID_REQUIRED");
        format!(
            "{:x}",
            Sha256::digest(format!("butler-development-build-context-v1\0{commit}\0{tree}"))
        )
    });
    if release
        && (digest.len() != 64
            || !digest
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()))
    {
        panic!("BUILD_CONTEXT_DIGEST_INVALID");
    }
    println!("cargo:rustc-env=BUTLER_BUILD_CONTEXT_DIGEST={digest}");
    let root_anchor = std::env::var("BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256").unwrap_or_default();
    if release
        && (root_anchor.len() != 64
            || !root_anchor
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()))
    {
        panic!("FIRSTSCREEN_ROOT_ANCHOR_REQUIRED");
    }
    if !root_anchor.is_empty() {
        println!("cargo:rustc-env=BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256={root_anchor}");
    }
    for (name, value) in [
        ("BUTLER_SOURCE_COMMIT_OID", source_commit.unwrap_or_default()),
        ("BUTLER_SOURCE_TREE_OID", source_tree.unwrap_or_default()),
    ] {
        let valid = matches!(value.len(), 40 | 64)
            && value
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase());
        if release && !valid {
            panic!("{name}_REQUIRED");
        }
        if valid {
            println!("cargo:rustc-env={name}={value}");
        }
    }
    tauri_build::build()
}
