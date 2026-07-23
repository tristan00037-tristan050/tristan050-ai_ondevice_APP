fn main() {
    println!("cargo:rerun-if-env-changed=BUTLER_BUILD_CONTEXT_DIGEST");
    println!("cargo:rerun-if-env-changed=BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256");
    println!("cargo:rerun-if-env-changed=BUTLER_SOURCE_COMMIT_OID");
    println!("cargo:rerun-if-env-changed=BUTLER_SOURCE_TREE_OID");
    let release = std::env::var("PROFILE").as_deref() == Ok("release");
    let digest = std::env::var("BUTLER_BUILD_CONTEXT_DIGEST").unwrap_or_else(|_| {
        if release {
            panic!("BUILD_CONTEXT_DIGEST_REQUIRED");
        }
        "development".to_string()
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
    for name in ["BUTLER_SOURCE_COMMIT_OID", "BUTLER_SOURCE_TREE_OID"] {
        let value = std::env::var(name).unwrap_or_default();
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
