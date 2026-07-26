pub const BUILD_CONTEXT_DIGEST: &str = env!("BUTLER_BUILD_CONTEXT_DIGEST");

/// "1" 이면 배포용 빌드(root bootstrap anchor 결속됨), 그 외에는 내부 빌드다.
/// 내부 빌드는 root 부트스트랩이 BLOCK_ROOT_BOOTSTRAP_ANCHOR 로 막힌다.
pub const RELEASE_DISTRIBUTION: &str = env!("BUTLER_RELEASE_DISTRIBUTION");

#[tauri::command]
pub fn get_native_release_distribution() -> bool {
    RELEASE_DISTRIBUTION == "1"
}

#[tauri::command]
pub fn get_native_build_context_digest() -> &'static str {
    BUILD_CONTEXT_DIGEST
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_context_identity_is_never_empty() {
        assert!(!BUILD_CONTEXT_DIGEST.is_empty());
    }

    #[test]
    fn release_distribution_marker_is_explicit() {
        assert!(matches!(RELEASE_DISTRIBUTION, "0" | "1"));
        assert_eq!(
            get_native_release_distribution(),
            RELEASE_DISTRIBUTION == "1"
        );
    }
}
