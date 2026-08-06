use base64::{engine::general_purpose::STANDARD, Engine as _};
use sha2::{Digest, Sha256};
use std::process::Command;

mod build_gate;
mod distribution_flag;

fn git_identity(argument: &str) -> Option<String> {
    let output = Command::new("git")
        .args(["rev-parse", argument])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    String::from_utf8(output.stdout)
        .ok()
        .map(|value| value.trim().to_owned())
}

fn main() {
    println!("cargo:rerun-if-changed=build_gate.rs");
    println!("cargo:rerun-if-changed=distribution_flag.rs");
    println!("cargo:rerun-if-env-changed=BUTLER_BUILD_CONTEXT_DIGEST");
    println!("cargo:rerun-if-env-changed=BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256");
    println!("cargo:rerun-if-env-changed=BUTLER_RELEASE_DISTRIBUTION");
    println!("cargo:rerun-if-env-changed=BUTLER_HELPER1_EXECUTION_PUBLIC_KEY_B64");
    println!("cargo:rerun-if-env-changed=BUTLER_HELPER1_EXECUTION_PUBLIC_KEY_SHA256");
    println!("cargo:rerun-if-env-changed=BUTLER_SOURCE_COMMIT_OID");
    println!("cargo:rerun-if-env-changed=BUTLER_SOURCE_TREE_OID");
    let release = std::env::var("PROFILE").as_deref() == Ok("release");
    // 배포 빌드 여부는 명시 플래그로만 켠다. 기본값은 내부 빌드다.
    // 근거: 대표 결정(2026-07-23) — 앱 배포 위변조 방지 체계는 배포 개시 전으로 이월.
    // root bootstrap anchor 는 그 이월된 owner root 키 세리머니의 산출물이라 아직 존재하지 않는다.
    let distribution = distribution_flag::release_distribution_from_env();
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
        let commit = source_commit
            .as_deref()
            .expect("SOURCE_COMMIT_OID_REQUIRED");
        let tree = source_tree.as_deref().expect("SOURCE_TREE_OID_REQUIRED");
        format!(
            "{:x}",
            Sha256::digest(format!(
                "butler-development-build-context-v1\0{commit}\0{tree}"
            ))
        )
    });
    let root_anchor = std::env::var("BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256").unwrap_or_default();
    let commit = source_commit.unwrap_or_default();
    let tree = source_tree.unwrap_or_default();

    // ★게이트는 build.rs 안에서 판정한다. shell wrapper 를 건너뛰고 cargo 나 build.rs 를
    //   직접 호출해도 같은 검사를 통과해야 한다. 판정 규칙은 build_gate.rs 한 곳에만 있다.
    let gate = build_gate::evaluate_build_gate(
        release,
        distribution,
        &root_anchor,
        &digest,
        &commit,
        &tree,
    )
    .unwrap_or_else(|code| panic!("{code}"));

    println!("cargo:rustc-env=BUTLER_BUILD_CONTEXT_DIGEST={digest}");
    // anchor 가 없으면 없는 채로 둔다. 임의 값으로 채우지 않는다.
    // 이 경우 runtime_trust 는 최초 root 부트스트랩에서 BLOCK_ROOT_BOOTSTRAP_ANCHOR 로 차단된다
    // (verifier.rs). 즉 신뢰 게이트는 제거되지 않고, 배포용이 아닌 앱이 될 뿐이다.
    if gate.emit_root_anchor {
        println!("cargo:rustc-env=BUTLER_FIRSTSCREEN_ROOT_ANCHOR_SHA256={root_anchor}");
    }
    println!(
        "cargo:rustc-env=BUTLER_RELEASE_DISTRIBUTION={}",
        u8::from(gate.distribution)
    );
    let helper1_key_b64 = std::env::var("BUTLER_HELPER1_EXECUTION_PUBLIC_KEY_B64").ok();
    let helper1_key_digest = std::env::var("BUTLER_HELPER1_EXECUTION_PUBLIC_KEY_SHA256").ok();
    match (helper1_key_b64, helper1_key_digest) {
        (None, None) => {}
        (Some(encoded), Some(expected)) if gate.distribution => {
            let decoded = STANDARD
                .decode(&encoded)
                .expect("HELPER1_EXECUTION_PUBLIC_KEY_INVALID");
            if decoded.len() != 32 || format!("{:x}", Sha256::digest(&decoded)) != expected {
                panic!("HELPER1_EXECUTION_TRUST_ROOT_MISMATCH");
            }
            println!("cargo:rustc-env=BUTLER_HELPER1_EXECUTION_PUBLIC_KEY_B64={encoded}");
            println!("cargo:rustc-env=BUTLER_HELPER1_EXECUTION_PUBLIC_KEY_SHA256={expected}");
        }
        _ => panic!("HELPER1_EXECUTION_TRUST_ROOT_INCOMPLETE"),
    }
    for (name, value) in [
        ("BUTLER_SOURCE_COMMIT_OID", commit),
        ("BUTLER_SOURCE_TREE_OID", tree),
    ] {
        if build_gate::is_object_id(&value) {
            println!("cargo:rustc-env={name}={value}");
        }
    }
    tauri_build::build()
}
