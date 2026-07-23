pub const BUILD_CONTEXT_DIGEST: &str = env!("BUTLER_BUILD_CONTEXT_DIGEST");

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
}
