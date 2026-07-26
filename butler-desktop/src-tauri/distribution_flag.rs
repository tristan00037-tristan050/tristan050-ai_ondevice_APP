pub const INVALID_DISTRIBUTION_FLAG: &str = "RELEASE_DISTRIBUTION_FLAG_INVALID";

pub fn parse_release_distribution(value: Option<&str>) -> Result<bool, &'static str> {
    match value {
        None | Some("0") => Ok(false),
        Some("1") => Ok(true),
        Some(_) => Err(INVALID_DISTRIBUTION_FLAG),
    }
}

#[cfg_attr(test, allow(dead_code))]
pub fn release_distribution_from_env() -> bool {
    match std::env::var("BUTLER_RELEASE_DISTRIBUTION") {
        Ok(value) => {
            parse_release_distribution(Some(&value)).unwrap_or_else(|code| panic!("{code}"))
        }
        Err(std::env::VarError::NotPresent) => false,
        Err(std::env::VarError::NotUnicode(_)) => {
            panic!("{INVALID_DISTRIBUTION_FLAG}")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_only_unset_zero_or_one() {
        assert_eq!(parse_release_distribution(None), Ok(false));
        assert_eq!(parse_release_distribution(Some("0")), Ok(false));
        assert_eq!(parse_release_distribution(Some("1")), Ok(true));
    }

    #[test]
    fn rejects_values_that_could_downgrade_a_distribution_build() {
        for value in ["", "true", "false", "yes", "2", " 1", "1 "] {
            assert_eq!(
                parse_release_distribution(Some(value)),
                Err(INVALID_DISTRIBUTION_FLAG),
                "{value:?}"
            );
        }
    }
}
