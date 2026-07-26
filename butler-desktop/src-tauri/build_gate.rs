//! 빌드 시점 출처·배포 게이트 판정.
//!
//! build.rs 와 크레이트 양쪽에서 같은 코드를 쓴다(build.rs 는 `include!` 로 끌어온다).
//! 그래야 게이트가 shell wrapper 가 아니라 ★빌드 자체에 붙는다. build.rs 를 직접
//! 호출하거나 cargo 를 직접 부르는 경로에서도 동일하게 작동한다.
//!
//! 의존성을 두지 않는다(순수 판정 함수). build script 문맥에서도 그대로 컴파일된다.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BuildGate {
    /// 배포용 빌드인가. release 프로파일 + 유효한 root anchor 가 모두 성립할 때만 참이다.
    pub distribution: bool,
    /// root anchor 를 rustc-env 로 내보낼지 여부. 없으면 내보내지 않는다(임의 값 금지).
    pub emit_root_anchor: bool,
}

pub fn is_lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

pub fn is_object_id(value: &str) -> bool {
    matches!(value.len(), 40 | 64)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

/// 실패하면 안정된 오류 코드를 돌려준다. 호출부는 이 코드로 그대로 panic 한다.
pub fn evaluate_build_gate(
    release: bool,
    distribution: bool,
    root_anchor: &str,
    context_digest: &str,
    source_commit: &str,
    source_tree: &str,
) -> Result<BuildGate, &'static str> {
    // ① 배포 플래그는 release 프로파일에서만 의미를 갖는다.
    //    이 결속이 없으면 debug + BUTLER_RELEASE_DISTRIBUTION=1 로 아래 검사를 전부 건너뛸 수 있다.
    if distribution && !release {
        return Err("DISTRIBUTION_REQUIRES_RELEASE_PROFILE");
    }

    // ② 배포 빌드는 root bootstrap anchor 가 반드시 있어야 한다.
    let root_anchor_valid = is_lower_hex(root_anchor, 64);
    if distribution && !root_anchor_valid {
        return Err("FIRSTSCREEN_ROOT_ANCHOR_REQUIRED");
    }

    // ③ 배포가 아니어도 값을 넘겼다면 형식은 지킨다. 잘못된 값이 조용히 박히지 않게 한다.
    if !root_anchor.is_empty() && !root_anchor_valid {
        return Err("FIRSTSCREEN_ROOT_ANCHOR_INVALID");
    }

    // ④ release 프로파일의 출처 3종은 배포 여부와 무관하게 필수다.
    if release {
        if !is_lower_hex(context_digest, 64) {
            return Err("BUILD_CONTEXT_DIGEST_INVALID");
        }
        if !is_object_id(source_commit) {
            return Err("BUTLER_SOURCE_COMMIT_OID_REQUIRED");
        }
        if !is_object_id(source_tree) {
            return Err("BUTLER_SOURCE_TREE_OID_REQUIRED");
        }
    }

    Ok(BuildGate {
        distribution,
        emit_root_anchor: root_anchor_valid,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const ANCHOR: &str = "9f1c0a4d2b6e8f3a5c7d9e1b3f5a7c9e1d3b5f7a9c1e3d5b7f9a1c3e5d7b9f1a";
    const DIGEST: &str = "56a060089a2b697d392888367c82db8c626bbed0fb218a299623843f930fe582";
    const COMMIT: &str = "1b31184e652d497995caae8c699b9cd13f84c7be";
    const TREE: &str = "0a85a295bbd7737108f52959e6117ab6b30d691b";

    // ── 재검토팀 지정 회귀 6조합 ──────────────────────────────

    #[test]
    fn debug_without_distribution_and_without_anchor_passes() {
        let gate =
            evaluate_build_gate(false, false, "", "", "", "").expect("debug 는 통과해야 한다");
        assert!(!gate.distribution);
        assert!(!gate.emit_root_anchor);
    }

    #[test]
    fn release_without_distribution_and_without_anchor_passes_as_non_distribution() {
        let gate = evaluate_build_gate(true, false, "", DIGEST, COMMIT, TREE)
            .expect("내부 빌드는 통과한다");
        assert!(!gate.distribution, "배포용이 아니어야 한다");
        assert!(!gate.emit_root_anchor, "anchor 를 임의로 채우지 않는다");
    }

    #[test]
    fn debug_with_distribution_is_rejected_regardless_of_anchor() {
        // ★핵심 폐쇄 조건: debug + 배포 플래그로 검사를 우회할 수 없다.
        for anchor in ["", "zz", ANCHOR] {
            assert_eq!(
                evaluate_build_gate(false, true, anchor, DIGEST, COMMIT, TREE),
                Err("DISTRIBUTION_REQUIRES_RELEASE_PROFILE"),
                "anchor={anchor:?}"
            );
        }
    }

    #[test]
    fn release_distribution_without_anchor_is_rejected() {
        assert_eq!(
            evaluate_build_gate(true, true, "", DIGEST, COMMIT, TREE),
            Err("FIRSTSCREEN_ROOT_ANCHOR_REQUIRED")
        );
    }

    #[test]
    fn release_distribution_with_malformed_anchor_is_rejected() {
        for anchor in [
            "a".repeat(63),
            "a".repeat(65),
            "A".repeat(64),
            "z".repeat(64),
            format!("sha256:{}", "a".repeat(57)),
        ] {
            assert_eq!(
                evaluate_build_gate(true, true, &anchor, DIGEST, COMMIT, TREE),
                Err("FIRSTSCREEN_ROOT_ANCHOR_REQUIRED"),
                "anchor={anchor:?}"
            );
        }
    }

    #[test]
    fn release_distribution_with_valid_anchor_and_identity_passes() {
        let gate = evaluate_build_gate(true, true, ANCHOR, DIGEST, COMMIT, TREE)
            .expect("배포 빌드 정상 조합은 통과한다");
        assert!(gate.distribution);
        assert!(gate.emit_root_anchor);
    }

    // ── 출처 3종은 배포 여부와 무관하게 release 필수 ──────────

    #[test]
    fn release_requires_source_identity_even_without_distribution() {
        assert_eq!(
            evaluate_build_gate(true, false, "", "", COMMIT, TREE),
            Err("BUILD_CONTEXT_DIGEST_INVALID")
        );
        assert_eq!(
            evaluate_build_gate(true, false, "", DIGEST, "", TREE),
            Err("BUTLER_SOURCE_COMMIT_OID_REQUIRED")
        );
        assert_eq!(
            evaluate_build_gate(true, false, "", DIGEST, COMMIT, ""),
            Err("BUTLER_SOURCE_TREE_OID_REQUIRED")
        );
    }

    #[test]
    fn release_distribution_still_requires_source_identity() {
        assert_eq!(
            evaluate_build_gate(true, true, ANCHOR, DIGEST, COMMIT, "beef"),
            Err("BUTLER_SOURCE_TREE_OID_REQUIRED")
        );
    }

    #[test]
    fn malformed_anchor_without_distribution_is_rejected() {
        assert_eq!(
            evaluate_build_gate(true, false, "not-a-digest", DIGEST, COMMIT, TREE),
            Err("FIRSTSCREEN_ROOT_ANCHOR_INVALID")
        );
    }
}
